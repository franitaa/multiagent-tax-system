"""Computation agent: derives Form 1040-SR lines by calling deterministic tools only.

Every returned line is a ProvenanceRecord (value, formula, inputs, source, tool). Amounts the
taxpayer typed in come back as direct-input records; amounts read from documents carry the
document id; everything else is produced by a registered tool. No arithmetic happens here.

Dependency order: income lines -> 6b (taxable Social Security) -> 9 total income -> 11 AGI ->
12 standard deduction -> 13b senior deduction (needs AGI) -> 15 taxable income -> 16 tax ->
24 total tax -> 33 total payments -> 34 refund / 37 amount owed.
"""
from provenance import make_direct_input_provenance, make_provenance

# Rules uses short codes; the tax tools use full names.
STATUS_NAMES = {
    "single": "single",
    "mfj": "married_filing_jointly",
    "mfs": "married_filing_separately",
    "hoh": "head_of_household",
    "qss": "qualifying_surviving_spouse",
}
FULL_NAMES = set(STATUS_NAMES.values())

# line -> {document kind: extracted field}. Assumed field names; see docs/provenance.md.
DOC_LINES = {
    "line_1a": {"w-2": "box_1"},
    "line_2b": {"1099-int": "box_1"},
    "line_3b": {"1099-div": "box_1a"},
    "line_4b": {"1099-r": "box_2a"},  # IRAs; pensions go to 5b below
    "line_6a": {"ssa-1099": "box_5"},
    "line_25a": {"w-2": "box_2", "1099-r": "box_4", "1099-int": "box_4", "1099-div": "box_4"},
}
TAX_EXEMPT_INTEREST = {"1099-int": "box_8"}


def _fact(facts, name, default=None):
    item = facts.get(name)
    return item.get("value", default) if isinstance(item, dict) else default


def _entered_by(facts, name):
    source = (facts.get(name) or {}).get("source", "user")
    return "taxpayer (via Intake)" if source == "user" else str(source)


def _doc_amounts(extracted, mapping):
    """(label, value, doc_id) for each extracted document field named in `mapping`."""
    found = []
    for doc_id, record in sorted(extracted.items()):
        field = mapping.get(str(record.get("kind", "")).strip().lower())
        item = (record.get("fields") or {}).get(field) if field else None
        value = item.get("value") if isinstance(item, dict) else item
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            found.append((f"{doc_id}.{field}", value, doc_id))
    return found


def _intake_status(facts):
    """TEMPORARY fallback until Rules writes eligibility["filing_status"] from the real Intake
    answers (docs/answer-names.md). Only unambiguous plain answers; otherwise None."""
    married, joint = _fact(facts, "married_dec31"), _fact(facts, "file_jointly")
    if married == "no" and _fact(facts, "household_situation") == "single":
        return "single"
    if married == "yes" and joint in ("yes", "no"):
        return "mfj" if joint == "yes" else "mfs"
    return None


def _status(view):
    facts, eligibility = view.get("facts", {}), view.get("eligibility") or {}
    raw = (_fact(facts, "filing_status") or eligibility.get("filing_status")
           or _fact(facts, "filing_status_claim") or _intake_status(facts))
    name = STATUS_NAMES.get(str(raw).strip().lower(), str(raw).strip().lower())
    if name not in FULL_NAMES:
        raise ValueError("Computation needs a valid filing status; Rules/Intake must supply it")
    return name


def _is_senior(age):
    return age is not None and age >= 65


def _senior_by_birth_date(value):
    """65 or older at the end of 2025 = born before January 2, 1961 (same cutoff as Rules)."""
    return isinstance(value, str) and value[:10] < "1961-01-02" if value[:4].isdigit() else False


def _is_65(facts, age_name, birth_name):
    age = _fact(facts, age_name)
    if age is not None:
        return _is_senior(age)
    return _senior_by_birth_date(str(_fact(facts, birth_name) or ""))


def _yes(facts, *names):
    return any(_fact(facts, n) in (True, "yes") for n in names)


def run(view, tools):
    facts, extracted = view.get("facts", {}), view.get("extracted", {})
    status = _status(view)
    computed = {}

    def call(tool, **kwargs):
        return tools.call(tool, **kwargs)

    def add(line, record):
        computed[line] = record
        return record["value"]

    def direct(line, fact_name):
        """Direct user input for `line`, or None when the taxpayer gave no amount."""
        value = _fact(facts, fact_name)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return None
        return add(line, make_direct_input_provenance(
            value, fact_name, _entered_by(facts, fact_name)))

    def from_documents(line, mapping):
        """Line total from documents. One document keeps its own source; several are summed."""
        amounts = _doc_amounts(extracted, mapping)
        if len(amounts) == 1:
            label, value, doc_id = amounts[0]
            return add(line, make_provenance(
                value, f"{line} = value read from document field {label}", {label: value},
                f"Document {doc_id} (Document Extraction)", "document_extraction"))
        record = call("sum_amounts", amounts={label: v for label, v, _ in amounts}, label=line)
        record["source"] = (
            "Documents: " + ", ".join(sorted({d for _, _, d in amounts}))
            if amounts else "No matching documents; amount is zero"
        )
        return add(line, record)

    # --- income lines (documents)
    wages = from_documents("line_1a", DOC_LINES["line_1a"])
    interest = from_documents("line_2b", DOC_LINES["line_2b"])
    dividends = from_documents("line_3b", DOC_LINES["line_3b"])
    ira = from_documents("line_4b", DOC_LINES["line_4b"])
    pensions = direct("line_5b", "pensions_taxable") or 0
    benefits = from_documents("line_6a", DOC_LINES["line_6a"])
    exempt = sum(v for _, v, _ in _doc_amounts(extracted, TAX_EXEMPT_INTEREST))

    # --- adjustments (Schedule 1, direct user input)
    adjustments = direct("line_10", "adjustments_amount")
    if adjustments is None:
        adjustments = add("line_10", call("sum_amounts", amounts={}, label="line_10"))
        computed["line_10"]["source"] = "No Schedule 1 adjustments entered"

    # --- 6b needs income other than Social Security, reduced by adjustments
    other_income = call(
        "subtract_amounts", start=wages + interest + dividends + ira + pensions,
        subtract={"line_10": adjustments}, label="income_before_social_security",
        start_name="lines_1a_2b_3b_4b_5b",
    )["value"]
    add("line_6b", call(
        "calculate_taxable_social_security", benefits=benefits, other_income=other_income,
        tax_exempt_interest=exempt, filing_status=status))

    total_income = add("line_9", call("sum_amounts", amounts={
        "line_1a": wages, "line_2b": interest, "line_3b": dividends, "line_4b": ira,
        "line_5b": pensions, "line_6b": computed["line_6b"]["value"]}, label="line_9"))
    agi = add("line_11", call(
        "subtract_amounts", start=total_income, subtract={"line_10": adjustments},
        label="line_11", start_name="line_9", floor_at_zero=False))

    # --- deductions
    senior_self = _is_65(facts, "age", "taxpayer_birth_date")
    joint = status == "married_filing_jointly"
    spouse_senior = joint and _is_65(facts, "spouse_age", "spouse_birth_date")
    std = add("line_12e", call(
        "calculate_standard_deduction", filing_status=status,
        age_65_or_older=senior_self, blind=_yes(facts, "blind", "taxpayer_blind"),
        spouse_age_65_or_older=spouse_senior,
        spouse_blind=joint and _yes(facts, "spouse_blind")))
    senior = add("line_13b", call(
        "calculate_senior_deduction", magi=max(0, agi),
        qualifying_people=int(senior_self) + int(spouse_senior), filing_status=status))
    deductions = call("sum_amounts", amounts={"line_12e": std, "line_13b": senior}, label="line_14")
    add("line_14", deductions)
    taxable = add("line_15", call(
        "subtract_amounts", start=agi, subtract={"line_14": deductions["value"]},
        label="line_15", start_name="line_11"))

    # --- tax (line 16 uses the tool, then Schedules 2/3 direct inputs)
    tax = add("line_16", call("calculate_income_tax", taxable_income=taxable, filing_status=status))
    schedule2 = direct("line_17", "schedule2_part1_tax") or 0
    credits = direct("line_20", "schedule3_nonrefundable_credits") or 0
    other_taxes = direct("line_23", "schedule2_other_taxes") or 0
    line_18 = add("line_18", call("sum_amounts", amounts={"line_16": tax, "line_17": schedule2},
                                  label="line_18"))
    line_22 = add("line_22", call(
        "subtract_amounts", start=line_18, subtract={"line_20": credits}, label="line_22",
        start_name="line_18"))
    total_tax = add("line_24", call(
        "sum_amounts", amounts={"line_22": line_22, "line_23": other_taxes}, label="line_24"))

    # --- payments
    withheld = from_documents("line_25a", DOC_LINES["line_25a"])
    estimated = direct("line_26", "estimated_payments_amount") or 0
    schedule3_payments = direct("line_31", "schedule3_payments") or 0
    payments = add("line_33", call("sum_amounts", amounts={
        "line_25a": withheld, "line_26": estimated, "line_31": schedule3_payments},
        label="line_33"))

    # --- refund or amount owed
    add("line_34", call(
        "subtract_amounts", start=payments, subtract={"line_24": total_tax}, label="line_34",
        start_name="line_33"))
    add("line_37", call(
        "subtract_amounts", start=total_tax, subtract={"line_33": payments}, label="line_37",
        start_name="line_24"))

    return {"computed": computed, "handoff_request": {"to": "review", "reason": "lines computed"}}
