"""Review/Audit agent. Owned by Person 6.

Independently tries to falsify the assembled return before any human sees it. It never
fixes anything: it reports findings and either passes the draft, sends it back to
Computation, or escalates when something out of scope slipped through.

Checks (each produces findings {check, line, issue, severity}):
  provenance      every line carries a complete ProvenanceRecord with a numeric value; a
                  "direct user input" record says who entered it and when, and matches the
                  amount the taxpayer gave (facts)
  sources         an input citing a document field ("<doc_id>.<field>") matches the extracted
                  value; an input citing a line ("line_9") matches that line; a line built only
                  from document fields equals their sum; every in-scope document amount
                  reaches its line (nothing dropped)
  recompute       lines produced by a deterministic tool are re-run through the same tool,
                  once with the record's own inputs (the record is honest) and once with
                  inputs re-derived from the return, eligibility and facts (the inputs are
                  right, including the 6b -> AGI ordering)
  totals          1z, 9, 11a, 14, 15, 24, 25d, 33, 34, 37 recomputed from their parts
  contradictions  3a <= 3b, 4b <= 4a, 5b <= 5a, 6b <= 6a and <= 85% of 6a, no negative
                  amounts, not both an overpayment and an amount owed
  completeness    the lines this return needs are present; every line is verifiable
  scope           eligibility in scope and 1040-SR eligible, only in-scope documents, no
                  1099-R with box 2b checked, no Schedule A/C/D/E or capital-gain lines, and
                  eligibility agrees with a filing status a volunteer decided

Errors fail the review (sent back to Computation). Scope problems also raise
OUT_OF_SCOPE / FORM_1099R_BOX_2B so a human sees them. Warnings never fail the review.

Review sees only the numeric answers in `facts` (amounts the taxpayer typed), never free
text such as dependents or volunteer notes. Blindness comes from Rules' line 12d box count,
a volunteer's filing status from `human_decisions`.

Review does its own arithmetic on purpose: the no-arithmetic rule binds Computation, whose
numbers are under test, not the auditor checking them.

Labels it checks against (docs/handoff-contract.md; taxpayer answers: docs/answer-names.md):
  computed keys   "line_<n>" as on the 1040-SR, e.g. line_1a, line_11a, line_25d
  document refs   provenance input "<doc_id>.<field>", e.g. "w2-1.box_1"
  extracted       {doc_id: {"kind": "W-2", "fields": {"box_1": {"value": ...} | value}}}
  typed amounts   source "direct user input" with entered_by and entered_on, as answer-names.md
  typed answers   provenance input "facts.<answer name>", checked against the numeric answer
"""
from src.state import ESCALATION_PRIORITY, FORM_1099R_BOX_2B, OUT_OF_SCOPE

TOLERANCE = 0.5  # dollars; covers whole-dollar rounding of a tool's cents result
MAX_FINDINGS = 20  # keeps the send-back (and the orchestrator's view) bounded
SEND_BACK_TARGET = "computation"
DIRECT_INPUT = "direct user input"  # a `source`, as in docs/answer-names.md
DIRECT_INPUT_TOOL = "make_direct_input_provenance"  # provenance.py helper for typed-in amounts
FACT_REF = "facts."  # an input taken from the taxpayer's typed answer: "facts.<answer name>"
REQUIRED_RECORD_KEYS = ("value", "formula", "inputs", "source", "tool")

FILING_STATUS_ALIASES = {
    "single": "single",
    "mfj": "married_filing_jointly",
    "married_filing_jointly": "married_filing_jointly",
    "mfs": "married_filing_separately",
    "married_filing_separately": "married_filing_separately",
    "hoh": "head_of_household",
    "head_of_household": "head_of_household",
    "qss": "qualifying_surviving_spouse",
    "qualifying_surviving_spouse": "qualifying_surviving_spouse",
}

IN_SCOPE_KINDS = frozenset({"w2", "ssa1099", "1099r", "1099int", "1099div"})

# (document kind, field) -> the lines that amount must reach.
DOC_FIELD_LINES = {
    ("w2", "box_1"): ("line_1a",),
    ("w2", "box_2"): ("line_25a",),
    ("1099int", "box_1"): ("line_2b",),
    ("1099int", "box_8"): ("line_2a",),
    ("1099int", "box_4"): ("line_25b",),
    ("1099div", "box_1a"): ("line_3b",),
    ("1099div", "box_1b"): ("line_3a",),
    ("1099div", "box_4"): ("line_25b",),
    ("1099r", "box_1"): ("line_4a", "line_5a"),
    ("1099r", "box_2a"): ("line_4b", "line_5b"),
    ("1099r", "box_4"): ("line_25b",),
    ("ssa1099", "box_5"): ("line_6a",),
    ("ssa1099", "box_6"): ("line_25b",),
}

# Lines produced by a deterministic tool, and the tool's parameters (must match tax_math).
TOOL_LINES = {
    "line_6b": "calculate_taxable_social_security",
    "line_12e": "calculate_standard_deduction",
    "line_13b": "calculate_senior_deduction",
    "line_16": "calculate_income_tax",
}
TOOL_PARAMS = {
    "calculate_standard_deduction": (
        "filing_status", "age_65_or_older", "blind", "spouse_age_65_or_older", "spouse_blind",
    ),
    "calculate_senior_deduction": ("magi", "qualifying_people", "filing_status"),
    "calculate_taxable_social_security": (
        "benefits", "other_income", "tax_exempt_interest", "filing_status",
    ),
    "calculate_income_tax": ("taxable_income", "filing_status"),
}

ALWAYS_REQUIRED = (
    "line_9", "line_11a", "line_12e", "line_14", "line_15", "line_16", "line_24", "line_33",
)
REQUIRED_BY_KIND = {
    "w2": ("line_1a", "line_1z"),
    "ssa1099": ("line_6a", "line_6b"),
    "1099int": ("line_2b",),
    "1099div": ("line_3b",),
}
OUT_OF_SCOPE_PREFIXES = ("schedule_a", "schedule_c", "schedule_d", "schedule_e")
NEGATIVE_ALLOWED = frozenset({"line_11a"})  # adjustments can exceed income
# (smaller, larger, what it means)
NOT_GREATER_THAN = (
    ("line_3a", "line_3b", "qualified dividends (3a) exceed ordinary dividends (3b)"),
    ("line_4b", "line_4a", "taxable IRA distributions (4b) exceed the total (4a)"),
    ("line_5b", "line_5a", "taxable pensions (5b) exceed the total (5a)"),
    ("line_6b", "line_6a", "taxable Social Security (6b) exceeds total benefits (6a)"),
)


# ---- helpers ------------------------------------------------------------------------


def _finding(check, line, issue, severity="error", condition=None):
    out = {"check": check, "line": line, "issue": issue, "severity": severity}
    if condition:
        out["condition"] = condition
    return out


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _amount(value):
    """A document amount as a number. Extraction may write text such as "20000.00"."""
    if _is_number(value):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip().replace("$", "").replace(",", ""))
        except ValueError:
            return None
    return None


def _close(a, b):
    return abs(a - b) <= TOLERANCE


def _kind(record):
    return str(record.get("kind", "")).lower().replace("-", "").replace(" ", "")


def _field(record, name):
    item = (record.get("fields") or {}).get(name)
    return item.get("value") if isinstance(item, dict) else item


def _fact(facts, name, default=None):
    item = facts.get(name)
    return item.get("value", default) if isinstance(item, dict) else default


def _is_direct_input(record):
    """An amount the taxpayer typed in. Recognised by the agreed source (Computation may add a note
    after it, e.g. "; NOT READ: ...") or by the provenance helper that makes these records."""
    source = str(record.get("source", "")).strip().lower()
    return source.startswith(DIRECT_INPUT) or record.get("tool") == DIRECT_INPUT_TOOL


def _status(value):
    return FILING_STATUS_ALIASES.get(str(value or "").strip().lower())


class _Return:
    """Read-only access to the computed lines; a missing line counts as zero in totals."""

    def __init__(self, computed):
        self.computed = computed

    def has(self, line):
        return line in self.computed

    def record(self, line):
        record = self.computed.get(line)
        return record if isinstance(record, dict) else {}  # malformed: reported by check_provenance

    def value(self, line):
        value = self.record(line).get("value")
        return float(value) if _is_number(value) else 0.0

    def tool(self, line):
        return self.record(line).get("tool")

    def inputs(self, line):
        inputs = self.record(line).get("inputs")
        return inputs if isinstance(inputs, dict) else {}


# ---- checks -------------------------------------------------------------------------


def check_direct_inputs(ret, facts):
    """A typed-in amount must equal what the taxpayer gave, when the record names the answer."""
    findings = []
    for line in sorted(ret.computed):
        record = ret.record(line)
        name = ret.inputs(line).get("field_name")
        if not (_is_direct_input(record) and name in facts):
            continue
        given = _amount(_fact(facts, name))
        if given is not None and not _close(given, ret.value(line)):
            findings.append(_finding(
                "provenance", line, f"is {ret.value(line)}, but the taxpayer gave {name} = {given}"))
    return findings


def check_provenance(computed):
    findings = []
    if not computed:
        return [_finding("completeness", None, "no computed lines to review")]
    for line, record in sorted(computed.items()):
        if not isinstance(record, dict):
            findings.append(_finding("provenance", line, "has no provenance record"))
            continue
        missing = [k for k in REQUIRED_RECORD_KEYS if k not in record]
        if missing:
            findings.append(_finding("provenance", line, f"provenance record lacks {missing}"))
        if not _is_number(record.get("value")):
            findings.append(_finding("provenance", line, "value is not a number"))
        if "inputs" in record and not isinstance(record["inputs"], dict):
            findings.append(_finding("provenance", line, "inputs is not a mapping"))
        for key in ("source", "tool", "formula"):
            if key in record and not str(record[key] or "").strip():
                findings.append(_finding("provenance", line, f"{key} is empty"))
        if _is_direct_input(record):
            inputs = record.get("inputs") if isinstance(record.get("inputs"), dict) else {}
            if not all(record.get(k) or inputs.get(k) for k in ("entered_by", "entered_on")):
                findings.append(_finding(
                    "provenance", line, "direct user input must record entered_by and entered_on"))
    return findings


def check_sources(ret, extracted, facts=None):
    """Every cited document field, typed answer or line matches; nothing from a document is dropped."""
    facts = facts or {}
    findings, verified = [], set()
    for line in sorted(ret.computed):
        record, inputs = ret.record(line), ret.inputs(line)
        doc_values = []
        for key, cited in inputs.items():
            if key.startswith(FACT_REF):
                # an amount the taxpayer typed in, checked against their (numeric) answer
                name = key[len(FACT_REF):]
                given = _amount(_fact(facts, name))
                if name not in facts:
                    findings.append(_finding("sources", line, f"cites {key}, which the taxpayer did not give"))
                elif given is None:
                    findings.append(_finding("sources", line, f"cites {key}, which is not an amount"))
                elif _amount(cited) is not None and not _close(_amount(cited), given):
                    findings.append(_finding(
                        "sources", line, f"uses {key} = {cited}, but the taxpayer gave {given}"))
                else:
                    doc_values.append(given)
            elif key.startswith("line_"):
                if not ret.has(key):
                    # a blank line is zero; citing it as zero is fine
                    if _is_number(cited) and not _close(cited, 0.0):
                        findings.append(_finding(
                            "sources", line, f"uses {key} = {cited}, but {key} is blank"))
                elif _is_number(cited) and not _close(cited, ret.value(key)):
                    findings.append(_finding(
                        "sources", line, f"uses {key} = {cited}, but {key} is {ret.value(key)}"))
            elif "." in key:
                doc_id, field = key.split(".", 1)
                if doc_id not in extracted:
                    findings.append(_finding("sources", line, f"cites {doc_id}, which was not extracted"))
                    continue
                raw = _field(extracted[doc_id], field)
                actual = _amount(raw)
                if raw is None:
                    findings.append(_finding("sources", line, f"cites {key}, which the document lacks"))
                elif actual is None:
                    findings.append(_finding("sources", line, f"cites {key}, which is not an amount"))
                elif _amount(cited) is not None and not _close(_amount(cited), actual):
                    findings.append(_finding(
                        "sources", line, f"uses {key} = {cited}, but the document shows {actual}"))
                else:
                    doc_values.append(actual)
        # a blank line (zero, built from nothing) needs no source; the document check below
        # still catches an amount that should have reached it
        if not inputs and _is_number(record.get("value")) and record["value"] == 0:
            verified.add(line)
        # a line built only from document fields and typed answers must equal their sum
        if inputs and len(doc_values) == len(inputs):
            verified.add(line)
            if _is_number(record.get("value")) and not _close(record["value"], sum(doc_values)):
                findings.append(_finding(
                    "sources", line,
                    f"is {record['value']}, but the cited document amounts sum to {sum(doc_values)}"))

    for doc_id, record in sorted(extracted.items()):
        if not isinstance(record, dict):
            continue
        kind = _kind(record)
        for (doc_kind, field), lines in DOC_FIELD_LINES.items():
            amount = _amount(_field(record, field)) if doc_kind == kind else None
            if not amount:
                continue
            ref = f"{doc_id}.{field}"
            if not any(ref in ret.inputs(line) for line in lines):
                findings.append(_finding(
                    "sources", lines[0], f"{doc_id} {field} ({amount}) does not reach {' or '.join(lines)}"))
    return findings, verified


def _blind_boxes(eligibility):
    """Blindness boxes on line 12d: Rules' box count minus the age boxes it found. None if the
    count does not fit the ages (reported as a finding)."""
    boxes = eligibility.get("age_blindness_boxes") or 0
    ages = int(eligibility.get("taxpayer_qualifies") is True) + int(eligibility.get("spouse_qualifies") is True)
    blind = boxes - ages if isinstance(boxes, int) else -1
    return blind if 0 <= blind <= 2 else None


def _derived_tool_inputs(line, ret, eligibility):
    """Inputs for `line`'s tool re-derived from the return and eligibility, not the record."""
    status = _status(eligibility.get("filing_status"))
    joint = status == "married_filing_jointly"
    taxpayer_65 = eligibility.get("taxpayer_qualifies") is True
    spouse_65 = eligibility.get("spouse_qualifies") is True
    if line == "line_12e":
        # each box adds the same amount, so only the count of blindness boxes matters
        blind = _blind_boxes(eligibility) or 0
        return {
            "filing_status": status,
            "age_65_or_older": taxpayer_65,
            "blind": blind >= 1,
            # spouse boxes only on a joint return (as Computation does)
            "spouse_age_65_or_older": joint and spouse_65,
            "spouse_blind": joint and blind >= 2,
        }
    if line == "line_13b":
        return {
            "magi": max(0.0, ret.value("line_11a")),
            "qualifying_people": int(taxpayer_65) + int(joint and spouse_65),
            "filing_status": status,
        }
    if line == "line_6b":
        # 6b depends on the rest of income: AGI without the benefits themselves
        return {
            "benefits": ret.value("line_6a"),
            "other_income": max(0.0, ret.value("line_11a") - ret.value("line_6b")),
            "tax_exempt_interest": ret.value("line_2a"),
            "filing_status": status,
        }
    if line == "line_16":
        return {"taxable_income": ret.value("line_15"), "filing_status": status}
    raise KeyError(line)


def check_recompute(ret, eligibility, tools):
    findings, verified = [], set()
    status = _status(eligibility.get("filing_status"))
    if ret.has("line_12e") and _blind_boxes(eligibility) is None:
        findings.append(_finding(
            "recompute", "line_12e",
            f"Rules' line 12d box count ({eligibility.get('age_blindness_boxes')}) does not fit the ages it found"))
    for line, tool in TOOL_LINES.items():
        if not ret.has(line):
            continue
        verified.add(line)
        if ret.tool(line) != tool:
            findings.append(_finding("recompute", line, f"was not produced by {tool}"))
            continue
        recorded = {k: v for k, v in ret.inputs(line).items() if k in TOOL_PARAMS[tool]}
        if _status(recorded.get("filing_status")) != status:
            findings.append(_finding(
                "recompute", line,
                f"used filing status {recorded.get('filing_status')!r}, eligibility says {status!r}"))
        # 1) the record is honest: its own inputs give its value
        try:
            replay = tools.call(tool, **recorded)["value"]
            if not _close(replay, ret.value(line)):
                findings.append(_finding(
                    "recompute", line, f"is {ret.value(line)}, but its own inputs give {replay}"))
        except (TypeError, ValueError) as exc:
            findings.append(_finding("recompute", line, f"its recorded inputs are invalid: {exc}"))
        # 2) the inputs are right: independently derived inputs give the same value
        derived = _derived_tool_inputs(line, ret, eligibility)
        try:
            expected = tools.call(tool, **derived)["value"]
        except (TypeError, ValueError) as exc:
            findings.append(_finding("recompute", line, f"cannot be recomputed: {exc}"))
            continue
        if not _close(expected, ret.value(line)):
            wrong = sorted(k for k, v in derived.items() if k in recorded and recorded[k] != v)
            hint = f" (inputs that differ: {wrong})" if wrong else ""
            findings.append(_finding(
                "recompute", line, f"is {ret.value(line)}, recomputed {expected}{hint}"))
    if ret.has("line_16") and ret.value("line_3a") > 0:
        findings.append(_finding(
            "recompute", "line_16",
            "qualified dividends (3a) are present but line 16 uses ordinary rate brackets only; "
            "the tax may be overstated (no qualified-dividend worksheet tool exists)",
            severity="warning"))
    return findings, verified


def _totals(ret):
    v = ret.value
    return {
        "line_1z": sum(v(f"line_1{c}") for c in "abcdefgh"),
        "line_9": sum(v(x) for x in (
            "line_1z", "line_2b", "line_3b", "line_4b", "line_5b", "line_6b", "line_7", "line_8")),
        "line_11a": v("line_9") - v("line_10"),
        "line_14": v("line_12e") + v("line_13a") + v("line_13b"),
        "line_15": max(0.0, v("line_11a") - v("line_14")),
        "line_18": v("line_16") + v("line_17"),
        "line_22": max(0.0, v("line_16") + v("line_17") - v("line_19") - v("line_20")),
        "line_24": max(0.0, v("line_16") + v("line_17") - v("line_19") - v("line_20")) + v("line_23"),
        "line_25d": v("line_25a") + v("line_25b") + v("line_25c"),
        # line 32 is the total of 27-31; use it when present, else its parts
        "line_33": v("line_25d") + v("line_26") + (
            v("line_32") if ret.has("line_32") else sum(v(f"line_{n}") for n in range(27, 32))),
        "line_34": max(0.0, v("line_33") - v("line_24")),
        "line_37": max(0.0, v("line_24") - v("line_33")),
    }


def check_totals(ret):
    findings, verified = [], set()
    for line, expected in _totals(ret).items():
        if not ret.has(line):
            continue
        verified.add(line)
        if not _close(ret.value(line), expected):
            findings.append(_finding("totals", line, f"is {ret.value(line)}, recomputed {round(expected, 2)}"))
    return findings, verified


def check_contradictions(ret):
    findings = []
    for line, record in sorted(ret.computed.items()):
        value = record.get("value") if isinstance(record, dict) else None
        if _is_number(value) and value < 0 and line not in NEGATIVE_ALLOWED:
            findings.append(_finding("contradictions", line, f"is negative ({value})"))
    for small, large, meaning in NOT_GREATER_THAN:
        if ret.has(small) and ret.has(large) and ret.value(small) > ret.value(large) + TOLERANCE:
            findings.append(_finding("contradictions", small, meaning))
    if ret.has("line_6b") and ret.has("line_6a") and ret.value("line_6b") > 0.85 * ret.value("line_6a") + TOLERANCE:
        findings.append(_finding("contradictions", "line_6b", "taxable Social Security exceeds 85% of benefits"))
    if ret.value("line_34") > 0 and ret.value("line_37") > 0:
        findings.append(_finding("contradictions", "line_34", "shows both an overpayment (34) and an amount owed (37)"))
    return findings


def check_completeness(ret, extracted, eligibility, verified):
    findings = []
    kinds = {_kind(r) for r in extracted.values() if isinstance(r, dict)}
    required = set(ALWAYS_REQUIRED)
    for kind in kinds:
        required.update(REQUIRED_BY_KIND.get(kind, ()))
    if "1099r" in kinds and not (ret.has("line_4a") or ret.has("line_5a")):
        findings.append(_finding("completeness", "line_4a", "a 1099-R was supplied but neither line 4a nor 5a is filled"))
    if eligibility.get("taxpayer_qualifies") is True or eligibility.get("spouse_qualifies") is True:
        required.add("line_13b")
    if not (ret.has("line_34") or ret.has("line_37")):
        findings.append(_finding("completeness", "line_34", "neither the overpayment (34) nor the amount owed (37) is filled"))
    for line in sorted(required - set(ret.computed)):
        findings.append(_finding("completeness", line, "is required for this return but missing"))
    for line in sorted(set(ret.computed) - verified):
        if not _is_direct_input(ret.record(line)):
            findings.append(_finding(
                "completeness", line, "cannot be verified: not a document sum, a known total, a "
                "tool result, or a recorded direct user input"))
    return findings


def check_scope(ret, extracted, eligibility, human_decisions):
    findings = []
    # False is a decision (escalate); None means Rules never decided (fail, do not mislabel)
    for key, what in (("in_scope", "whether the return is in scope"),
                      ("eligible_1040sr", "Form 1040-SR eligibility")):
        if eligibility.get(key) is False:
            findings.append(_finding("scope", None, f"Rules decided against {what}",
                                     condition=OUT_OF_SCOPE))
        elif eligibility.get(key) is not True:
            findings.append(_finding("scope", None, f"Rules has not decided {what}"))
    for doc_id, record in sorted(extracted.items()):
        if not isinstance(record, dict):
            continue
        kind = _kind(record)
        if kind not in IN_SCOPE_KINDS:
            findings.append(_finding("scope", None, f"{doc_id} is a {record.get('kind')!r}, which is out of scope",
                                     condition=OUT_OF_SCOPE))
        if kind == "1099r" and _field(record, "box_2b"):
            findings.append(_finding("scope", None, f"{doc_id} has box 2b 'taxable amount not determined' checked",
                                     condition=FORM_1099R_BOX_2B))
    for line in sorted(ret.computed):
        if line.startswith(OUT_OF_SCOPE_PREFIXES):
            findings.append(_finding("scope", line, "belongs to a schedule SilverFile does not handle",
                                     condition=OUT_OF_SCOPE))
    if ret.value("line_7") != 0:
        findings.append(_finding("scope", "line_7", "capital gains are out of scope", condition=OUT_OF_SCOPE))
    for decision in human_decisions:
        decided = (decision.get("resolution") or {}).get("filing_status")
        if decided and _status(decided) != _status(eligibility.get("filing_status")):
            findings.append(_finding(
                "scope", None, "eligibility does not use the filing status the volunteer decided"))
    return findings


# ---- agent --------------------------------------------------------------------------


def _bounded(findings):
    ordered = sorted(findings, key=lambda f: f["severity"] != "error")  # errors first, stable
    if len(ordered) <= MAX_FINDINGS:
        return ordered
    rest = len(ordered) - (MAX_FINDINGS - 1)
    return [*ordered[:MAX_FINDINGS - 1], _finding("review", None, f"and {rest} more findings")]


def _escalation(findings, view):
    resolved = {d.get("condition") for d in view.get("human_decisions", [])}
    raised = {f["condition"] for f in findings if f.get("condition") and f["condition"] not in resolved}
    if not raised:
        return None
    condition = min(raised, key=ESCALATION_PRIORITY.index)
    return {
        "pending": True,
        "condition": condition,
        "reason": f"Review found {len(raised)} scope problem(s) that slipped through: {sorted(raised)}",
        "raised_by": "review",
    }


def review_return(view, tools):
    """All checks over the view; returns the findings, most severe first, unbounded."""
    computed = view.get("computed") or {}
    extracted = view.get("extracted") or {}
    eligibility = view.get("eligibility") or {}
    facts = view.get("facts") or {}
    ret = _Return(computed)

    source_findings, doc_verified = check_sources(ret, extracted, facts)
    recompute_findings, tool_verified = check_recompute(ret, eligibility, tools)
    total_findings, total_verified = check_totals(ret)
    verified = doc_verified | tool_verified | total_verified
    return [
        *check_scope(ret, extracted, eligibility, view.get("human_decisions") or []),
        *check_provenance(computed),
        *check_direct_inputs(ret, facts),
        *source_findings,
        *recompute_findings,
        *total_findings,
        *check_contradictions(ret),
        *check_completeness(ret, extracted, eligibility, verified),
    ]


def run(view, tools):
    findings = review_return(view, tools)
    escalation = _escalation(findings, view)
    failed = escalation is not None or any(f["severity"] == "error" for f in findings)
    n_errors = sum(f["severity"] == "error" for f in findings)
    update = {
        "review": {
            "verdict": "fail" if failed else "pass",
            "findings": _bounded(findings),
            "send_back_to": SEND_BACK_TARGET if failed else None,
        },
    }
    if escalation:
        update["escalation"] = escalation
        update["handoff_request"] = {"to": "human", "reason": "out-of-scope item found in review"}
    elif failed:
        update["handoff_request"] = {"to": SEND_BACK_TARGET, "reason": f"{n_errors} review errors"}
    else:
        update["handoff_request"] = {"to": "end", "reason": "review passed"}
    return update
