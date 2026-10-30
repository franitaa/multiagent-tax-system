"""Computation agent: derives Form 1040-SR lines by calling deterministic tools only.

Every returned line is a ProvenanceRecord (value, formula, inputs, source, tool). Amounts the
taxpayer typed in come back as direct-input records; amounts read from documents carry the
document id; everything else is produced by a registered tool. No arithmetic happens here.

Line ids follow Assignment 7 section 3.1: 1z, 2a/2b, 3a/3b, 4a/4b, 5a/5b, 6a/6b, 9, 10, 11a,
12e, 13b, 14, 15, 16, 24, 25a-25d, 26, 33, 34/37 (plus 17-23 and 31 for Schedules 2 and 3).

Dependency order: document and direct-input lines -> 6b (needs the rest of income) -> 9 total
income -> 11a AGI -> 12e standard deduction -> 13b senior deduction (needs AGI) -> 14 -> 15
taxable income -> 16 tax -> 18/22/24 total tax -> 25d, 33 total payments -> 34 refund / 37 owed.

Review send-backs: when Review fails a draft it puts its findings in view["pending_revision"]
({"target", "round", "findings": [{"check", "line", "issue"}]}). Computation re-runs the whole
pipeline and, for the two kinds of finding it can fix without guessing, changes how it reads its
inputs (see _repairs): a "sources" finding (a document amount that did not reach its line) makes
it read text amounts such as "20000.00" as numbers; a "recompute" finding about the filing
status makes it use the status in `eligibility`. The first pass stays strict: a text amount is
not used until Review has flagged it. Findings it cannot act on are ignored; the loop bound
then hands the case to a human.

Forms that were not read (issue #27): Extraction reads only the W-2, so an SSA-1099, 1099-INT or
1099-DIV leaves no amounts behind. Computation does not turn that into a quiet zero: the lines the
form feeds say in their source that the form was not read, and `unread_forms` lets the draft form
warn. It never invents an amount, and it does not stop the case (that routing is Orchestration's).

Defensive escalations (Rules should catch these first): a taxpayer who can be claimed as a
dependent, or a separately filing spouse who itemizes (the Standard Deduction Chart does not
apply), a 1099-R whose taxable amount is not determined, and out-of-scope 1099 types.
"""
from provenance import make_direct_input_provenance, make_provenance
from src.income_forms import (DOC_LINES, TYPED_AMOUNTS, answered_yes, as_number, document_amounts, document_kind,
                              fact_value, record_field, text_amount, typed_amounts, unread_forms)
from src.state import FORM_1099R_BOX_2B, OUT_OF_SCOPE

# Rules uses short codes; the tax tools use full names.
STATUS_NAMES = {
    "single": "single",
    "mfj": "married_filing_jointly",
    "mfs": "married_filing_separately",
    "hoh": "head_of_household",
    "qss": "qualifying_surviving_spouse",
}
FULL_NAMES = set(STATUS_NAMES.values())

DIRECT_INPUT = "direct user input"  # the source Review accepts for an amount the taxpayer typed
OUT_OF_SCOPE_KINDS = ("1099nec", "1099misc", "1099b", "1099k")

def _entered_by(facts, name):
    source = (facts.get(name) or {}).get("source", "user")
    return "taxpayer (via Intake)" if source in ("user", "direct user input") else str(source)


def _repairs(view):
    """What Review's send-back lets Computation change. Returns (read_text, status_from_eligibility,
    what it did, for the handoff reason). Reads findings by their `check` and, for the filing
    status, the words 'filing status' in the issue; anything else is not acted on."""
    revision = view.get("pending_revision") or {}
    findings = [f for f in revision.get("findings") or [] if isinstance(f, dict)]
    read_text = any(f.get("check") == "sources" for f in findings)
    status = any(f.get("check") == "recompute" and "filing status" in str(f.get("issue", "")).lower()
                 for f in findings)
    done = (["read text amounts as numbers"] if read_text else []) + (
        ["used the filing status from eligibility"] if status else [])
    return read_text, status, done


def _status(view, prefer_eligibility=False):
    """The filing status. Normally a volunteer's override (facts) comes first; after Review says a
    tool used the wrong status, the status Rules put in `eligibility` comes first, unless the
    status in `facts` is a volunteer's decision."""
    facts, eligibility = view.get("facts", {}), view.get("eligibility") or {}
    decided = eligibility.get("filing_status")
    human = str((facts.get("filing_status") or {}).get("source", "")).startswith("human:")
    # a volunteer's decision is never overridden: if eligibility disagrees with it, that is for
    # Rules to fix and Review keeps failing the return until it does
    if (prefer_eligibility and not human
            and STATUS_NAMES.get(str(decided).strip().lower(), decided) in FULL_NAMES):
        raw = decided
    else:
        raw = (fact_value(facts, "filing_status") or decided
               or fact_value(facts, "filing_status_claim") or _intake_status(facts))
    name = STATUS_NAMES.get(str(raw).strip().lower(), str(raw).strip().lower())
    if name not in FULL_NAMES:
        raise ValueError("Computation needs a valid filing status; Rules/Intake must supply it")
    return name


def _intake_status(facts):
    """TEMPORARY fallback until Rules writes eligibility["filing_status"] from the real Intake
    answers (docs/answer-names.md). Only unambiguous plain answers; otherwise None."""
    married, joint = fact_value(facts, "married_dec31"), fact_value(facts, "file_jointly")
    if married == "no" and fact_value(facts, "household_situation") == "single":
        return "single"
    if married == "yes" and joint in ("yes", "no"):
        return "mfj" if joint == "yes" else "mfs"
    return None


def _is_65(facts, age_name, birth_name):
    """65 or older at the end of 2025 = born before January 2, 1961 (the Rules cutoff)."""
    age = fact_value(facts, age_name)
    if age is not None:
        return age >= 65
    birth = str(fact_value(facts, birth_name) or "")
    return birth[:4].isdigit() and birth[:10] < "1961-01-02"


def _escalate(condition, reason):
    return {
        "escalation": {"pending": True, "condition": condition, "reason": reason,
                       "raised_by": "computation"},
        "handoff_request": {"to": "human", "reason": condition},
    }


def _must_escalate(view, status):
    """First escalation that applies (and was not already resolved by a human), else None."""
    facts, extracted = view.get("facts", {}), view.get("extracted", {})
    resolved = {d.get("condition") for d in view.get("human_decisions", [])}

    def raise_once(condition, reason):
        return None if condition in resolved else _escalate(condition, reason)

    for record in extracted.values():
        if document_kind(record).startswith("1099r"):
            taxable = record_field(record, "box_2a")  # present as text counts: "determined" is not "a number"
            if record_field(record, "box_2b") or (as_number(taxable) is None and text_amount(taxable) is None):
                return raise_once(FORM_1099R_BOX_2B, "1099-R taxable amount not determined")
        if any(document_kind(record).startswith(k) for k in OUT_OF_SCOPE_KINDS):
            return raise_once(OUT_OF_SCOPE, "out-of-scope tax document")
    if answered_yes(facts, "can_be_claimed_as_dependent"):
        return raise_once(OUT_OF_SCOPE, "Standard Deduction Chart does not apply: can be claimed as a dependent")
    if status == "married_filing_separately" and answered_yes(facts, "spouse_itemizing"):
        return raise_once(OUT_OF_SCOPE, "Standard Deduction Chart does not apply: spouse itemizes")
    return None


def run(view, tools):
    facts, extracted = view.get("facts", {}), view.get("extracted", {})
    read_text, status_from_eligibility, repaired = _repairs(view)
    status = _status(view, status_from_eligibility)
    escalation = _must_escalate(view, status)
    if escalation:
        return escalation
    computed = {}
    unread = unread_forms(facts, extracted, read_text)

    def call(tool, **kwargs):
        return tools.call(tool, **kwargs)

    def add(line, record):
        computed[line] = record
        return record["value"]

    def direct(line, fact_name):
        """Direct user input for `line`, or None when the taxpayer gave no amount."""
        value = as_number(facts.get(fact_name))
        if value is None:
            return None
        return add(line, make_direct_input_provenance(
            value, fact_name, _entered_by(facts, fact_name)))

    def total(line, amounts, source=None):
        record = call("sum_amounts", amounts=amounts, label=line)
        if source:
            record["source"] = source
        return add(line, record)

    def from_documents(line):
        """Line total from documents and from amounts the taxpayer typed in (issue #27, step 2). One
        document keeps its own source; a single typed amount is a direct-input record; several are
        summed. A line fed by a form that was not read says so in its source, rather than passing as
        a plain zero."""
        amounts = document_amounts(extracted, DOC_LINES[line], read_text)
        # a form that was read from a document is not also counted from what was typed (no double count)
        read_kinds = {document_kind(extracted[d]) for _, _, d in amounts}
        ignored = [name for name, _ in typed_amounts(facts, line) if TYPED_AMOUNTS[name][0] in read_kinds]
        typed = [(n, v) for n, v in typed_amounts(facts, line) if n not in ignored]
        missing = [u["form"] for u in unread if line in u["lines"]]
        note = (f"; NOT READ: {', '.join(missing)} amounts were not captured, so this line may be "
                "understated") if missing else ""
        if ignored:
            note = f"{note}; typed {', '.join(ignored)} not used: the document was read"
        if not amounts and len(typed) == 1:
            name, value = typed[0]
            # Review accepts a typed amount only with source exactly "direct user input" (answer-names.md),
            # so a note about another unread form goes in the formula, not the source
            record = make_direct_input_provenance(value, name, _entered_by(facts, name))
            record["source"] = DIRECT_INPUT
            record["formula"] = f"{record['formula']}{note}"
            return add(line, record)
        if len(amounts) == 1 and not typed:
            label, value, doc_id = amounts[0]
            raw = record_field(extracted[doc_id], label.split(".", 1)[1])
            text = f" (text {raw!r} read as a number after a review finding)" if isinstance(raw, str) else ""
            return add(line, make_provenance(
                value, f"{line} = value read from document field {label}{text}", {label: value},
                f"Document {doc_id} (Document Extraction){note}", "document_extraction"))
        if amounts or typed:
            sources = ["Documents: " + ", ".join(sorted({d for _, _, d in amounts}))] if amounts else []
            if typed:
                sources.append("typed by taxpayer: " + ", ".join(name for name, _ in typed))
            source = "; ".join(sources)
        else:
            source = "No amount read; shown as zero" if missing else "No matching documents; amount is zero"
        parts = {label: v for label, v, _ in amounts}
        parts.update({f"facts.{name}": v for name, v in typed})
        return total(line, parts, f"{source}{note}")

    # --- income lines (documents), totals (a) and taxable (b)
    wages = total("line_1z", {"line_1a": from_documents("line_1a")},
                  "Total of W-2 wages (line 1a)")
    from_documents("line_2a")
    interest = from_documents("line_2b")
    from_documents("line_3a")
    dividends = from_documents("line_3b")
    from_documents("line_4a")
    ira = from_documents("line_4b")
    from_documents("line_5a")
    pensions = from_documents("line_5b")
    benefits = from_documents("line_6a")
    exempt = computed["line_2a"]["value"]

    def direct_or_zero(line, fact_name, note):
        """Direct user input for `line`; when none was entered, a tool-made zero that says so."""
        value = direct(line, fact_name)
        return value if value is not None else total(line, {}, note)

    # --- adjustments (Schedule 1, direct user input)
    adjustments = direct_or_zero("line_10", "adjustments_amount", "No Schedule 1 adjustments entered")

    # --- 6b needs income other than Social Security, reduced by adjustments
    income_before_benefits = call("sum_amounts", amounts={
        "line_1z": wages, "line_2b": interest, "line_3b": dividends, "line_4b": ira,
        "line_5b": pensions}, label="income_before_social_security_and_adjustments")["value"]
    other_income = call(
        "subtract_amounts", start=income_before_benefits,
        subtract={"line_10": adjustments}, label="income_before_social_security",
        start_name="lines_1z_2b_3b_4b_5b",
    )["value"]
    add("line_6b", call(
        "calculate_taxable_social_security", benefits=benefits, other_income=other_income,
        tax_exempt_interest=exempt, filing_status=status))

    total_income = total("line_9", {
        "line_1z": wages, "line_2b": interest, "line_3b": dividends, "line_4b": ira,
        "line_5b": pensions, "line_6b": computed["line_6b"]["value"]})
    agi = add("line_11a", call(
        "subtract_amounts", start=total_income, subtract={"line_10": adjustments},
        label="line_11a", start_name="line_9", floor_at_zero=False))

    # --- deductions
    # age 65+: the answer Rules decided when it gave one (Review checks the boxes against it),
    # else worked out from the taxpayer's own answers
    decided = view.get("eligibility") or {}
    senior_self = (decided["taxpayer_qualifies"] if isinstance(decided.get("taxpayer_qualifies"), bool)
                   else _is_65(facts, "age", "taxpayer_birth_date"))
    joint = status == "married_filing_jointly"
    spouse_senior = joint and (decided["spouse_qualifies"] if isinstance(decided.get("spouse_qualifies"), bool)
                               else _is_65(facts, "spouse_age", "spouse_birth_date"))
    std = add("line_12e", call(
        "calculate_standard_deduction", filing_status=status,
        age_65_or_older=senior_self, blind=answered_yes(facts, "blind", "taxpayer_blind"),
        spouse_age_65_or_older=spouse_senior,
        spouse_blind=joint and answered_yes(facts, "spouse_blind")))
    # the tool needs MAGI that is not negative, and a count of qualifying people; both come from tools
    magi = call("subtract_amounts", start=agi, subtract={}, label="magi_for_senior_deduction",
                start_name="line_11a")["value"]
    qualifying = int(call("sum_amounts", amounts={
        "taxpayer_65_or_older": int(senior_self), "spouse_65_or_older": int(spouse_senior)},
        label="qualifying_people")["value"])
    senior = add("line_13b", call(
        "calculate_senior_deduction", magi=magi, qualifying_people=qualifying,
        filing_status=status))
    deductions = total("line_14", {"line_12e": std, "line_13b": senior})
    taxable = add("line_15", call(
        "subtract_amounts", start=agi, subtract={"line_14": deductions},
        label="line_15", start_name="line_11a"))

    # --- tax (line 16 uses the rate schedule tool, then Schedules 2/3 direct inputs)
    tax = add("line_16", call("calculate_income_tax", taxable_income=taxable, filing_status=status))
    schedule2 = direct_or_zero("line_17", "schedule2_part1_tax", "No Schedule 2 tax entered")
    credits = direct_or_zero("line_20", "schedule3_nonrefundable_credits",
                             "No Schedule 3 credits entered")
    other_taxes = direct_or_zero("line_23", "schedule2_other_taxes", "No other taxes entered")
    line_18 = total("line_18", {"line_16": tax, "line_17": schedule2})
    line_22 = add("line_22", call(
        "subtract_amounts", start=line_18, subtract={"line_20": credits}, label="line_22",
        start_name="line_18"))
    total_tax = total("line_24", {"line_22": line_22, "line_23": other_taxes})

    # --- payments
    withheld_w2 = from_documents("line_25a")
    withheld_1099 = from_documents("line_25b")
    withheld = total("line_25d", {"line_25a": withheld_w2, "line_25b": withheld_1099})
    estimated = direct_or_zero("line_26", "estimated_payments_amount",
                              "No estimated payments entered")
    schedule3_payments = direct_or_zero("line_31", "schedule3_payments",
                                       "No Schedule 3 payments entered")
    payments = total("line_33", {
        "line_25d": withheld, "line_26": estimated, "line_31": schedule3_payments})

    # --- refund or amount owed
    add("line_34", call(
        "subtract_amounts", start=payments, subtract={"line_24": total_tax}, label="line_34",
        start_name="line_33"))
    add("line_37", call(
        "subtract_amounts", start=total_tax, subtract={"line_33": payments}, label="line_37",
        start_name="line_24"))

    reason = "lines computed" + (f" again after review: {', '.join(repaired)}" if repaired else "")
    return {"computed": computed, "handoff_request": {"to": "review", "reason": reason}}
