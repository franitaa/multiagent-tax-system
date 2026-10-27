"""Render a DRAFT Form 1040-SR page where every dollar amount expands (click, or keyboard) to show
its provenance: formula, inputs, source and tool. Plain HTML <details>; no dependencies.

The page is a draft for a human reviewer, never a filed return, and it is the audit record for the
case: besides the lines it shows the filing status and who set it, each line 12d box, the
dependents, what Review found (and how many rounds it took), and every volunteer decision.
Dependents' SSNs are masked and only valid 900-series test numbers are displayed
(security.is_fake_ssn). Everything shown is HTML-escaped; document text can reach these fields.

Large type, a real table with row headers, keyboard-operable details, "Show all sources" and a
print path that opens every source first."""
from html import escape
from pathlib import Path

from security import is_fake_ssn, redact_pii

SECTIONS = (
    ("Income", (
        ("line_1a", "1a", "Wages from Form(s) W-2"),
        ("line_1z", "1z", "Total wages"),
        ("line_2a", "2a", "Tax-exempt interest"),
        ("line_2b", "2b", "Taxable interest"),
        ("line_3a", "3a", "Qualified dividends"),
        ("line_3b", "3b", "Ordinary dividends"),
        ("line_4a", "4a", "IRA distributions"),
        ("line_4b", "4b", "IRA distributions, taxable amount"),
        ("line_5a", "5a", "Pensions and annuities"),
        ("line_5b", "5b", "Pensions and annuities, taxable amount"),
        ("line_6a", "6a", "Social Security benefits"),
        ("line_6b", "6b", "Social Security benefits, taxable amount"),
        ("line_9", "9", "Total income"),
        ("line_10", "10", "Adjustments to income (Schedule 1, line 26)"),
        ("line_11a", "11a", "Adjusted gross income"),
    )),
    ("Standard deduction and taxable income", (
        ("line_12e", "12e", "Standard deduction"),
        ("line_13b", "13b", "Additional deductions (Schedule 1-A senior deduction)"),
        ("line_14", "14", "Total deductions"),
        ("line_15", "15", "Taxable income"),
    )),
    ("Tax", (
        ("line_16", "16", "Tax"),
        ("line_17", "17", "Amount from Schedule 2, part I"),
        ("line_18", "18", "Add lines 16 and 17"),
        ("line_20", "20", "Amount from Schedule 3 (nonrefundable credits)"),
        ("line_22", "22", "Tax after credits"),
        ("line_23", "23", "Other taxes (Schedule 2)"),
        ("line_24", "24", "Total tax"),
    )),
    ("Payments", (
        ("line_25a", "25a", "Federal tax withheld from Form(s) W-2"),
        ("line_25b", "25b", "Federal tax withheld from Form(s) 1099"),
        ("line_25d", "25d", "Total federal tax withheld"),
        ("line_26", "26", "Estimated tax payments"),
        ("line_31", "31", "Amount from Schedule 3 (other payments)"),
        ("line_33", "33", "Total payments"),
    )),
    ("Refund or amount you owe", (
        ("line_34", "34", "Overpaid (refund)"),
        ("line_37", "37", "Amount you owe"),
    )),
)
LINE_LABELS = {line: f"{num}  {label}" for _, rows in SECTIONS for line, num, label in rows}
STATUS_LABELS = {
    "single": "Single", "mfj": "Married filing jointly", "mfs": "Married filing separately",
    "hoh": "Head of household", "qss": "Qualifying surviving spouse",
    "married_filing_jointly": "Married filing jointly",
    "married_filing_separately": "Married filing separately",
    "head_of_household": "Head of household",
    "qualifying_surviving_spouse": "Qualifying surviving spouse",
}
REQUIRED = {"value", "formula", "inputs", "source", "tool"}

# Line 12d: the four boxes, read from the inputs the standard-deduction tool was actually given.
BOXES_12D = (
    ("age_65_or_older", "You: born before January 2, 1961 (65 or older)"),
    ("blind", "You: blind"),
    ("spouse_age_65_or_older", "Spouse: born before January 2, 1961 (65 or older)"),
    ("spouse_blind", "Spouse: blind"),
)

STYLE = (
    "body{font-family:Arial,sans-serif;font-size:1.15rem;line-height:1.45;max-width:52rem;"
    "margin:2rem auto;padding:0 1rem;color:#111}"
    "h1{font-size:1.7rem}h2{font-size:1.3rem;margin-top:1.6rem}"
    "table{width:100%;border-collapse:collapse;margin-bottom:1rem}"
    "th,td{border-bottom:1px solid #ccc;padding:.5rem;text-align:left;vertical-align:top}"
    "th[scope=row]{width:3.5rem}.amt{text-align:right;width:12rem}"
    "summary{cursor:pointer;color:#0645ad;font-weight:bold}"
    "summary:focus{outline:3px solid #0645ad;outline-offset:2px}"
    "details p,details ul{text-align:left;margin:.2rem 0}"
    ".banner{background:#fff3cd;border:1px solid #d6b656;padding:.6rem}"
    ".ok{color:#0b5d1e;font-weight:bold}.bad{color:#9b1c1c;font-weight:bold}"
    "button{font-size:1rem;padding:.4rem .8rem;margin:0 .4rem .6rem 0}"
    "@media print{button{display:none}body{font-size:1rem;margin:0}}"
)

# Open every source before printing and put them back afterwards. Optional: with scripts off the
# page still works, one click at a time.
SCRIPT = (
    "(function(){var all=function(){return document.querySelectorAll('details')};"
    "var set=function(o){all().forEach(function(d){d.open=o})};"
    "document.getElementById('open-all').onclick=function(){set(true)};"
    "document.getElementById('close-all').onclick=function(){set(false)};"
    "document.getElementById('print').onclick=function(){window.print()};"
    "var was=[];window.addEventListener('beforeprint',function(){was=[];all().forEach(function(d){"
    "was.push(d.open);d.open=true})});"
    "window.addEventListener('afterprint',function(){all().forEach(function(d,i){d.open=was[i]})});"
    "})();"
)


def _money(value) -> str:
    return f"-${-value:,.2f}" if value < 0 else f"${value:,.2f}"


def _check(computed: dict) -> None:
    for line, record in computed.items():
        if not isinstance(record, dict):
            raise ValueError(f"{line} has no provenance record")
        missing = REQUIRED - set(record)
        if missing:
            raise ValueError(f"{line} has no provenance for: {sorted(missing)}")


def _amount_row(num: str, label: str, record: dict) -> str:
    inputs = "".join(
        f"<li>{escape(str(k))}: {escape(str(v))}</li>" for k, v in record["inputs"].items()
    ) or "<li>(none)</li>"
    amount = _money(record["value"])
    return (
        f"<tr><th scope='row'>{escape(num)}</th><td>{escape(label)}</td><td class='amt'>"
        f"<details><summary aria-label='{escape(label)}: {amount}. Show how this was produced.' "
        f"title='Click to see how this was produced'>{amount}</summary>"
        f"<p><b>Formula:</b> {escape(str(record['formula']))}</p>"
        f"<p><b>Inputs:</b></p><ul>{inputs}</ul>"
        f"<p><b>Source:</b> {escape(str(record['source']))}</p>"
        f"<p><b>Tool:</b> {escape(str(record['tool']))}</p></details></td></tr>"
    )


def _fact(facts, name):
    item = (facts or {}).get(name)
    return item.get("value") if isinstance(item, dict) else None


def _status(facts, eligibility):
    """(label, who set it). A volunteer's override (facts) wins over Rules' own decision, as it
    does in Computation."""
    override = (facts or {}).get("filing_status")
    if isinstance(override, dict) and override.get("value"):
        by = "a volunteer's decision" if str(override.get("source", "")).startswith("human:") else "the taxpayer's answer"
        status = override["value"]
    else:
        status, by = (eligibility or {}).get("filing_status"), "Eligibility & Rules"
    if not status:
        return "not yet determined", ""
    return STATUS_LABELS.get(status, str(status)), by


def _boxes_12d(computed, eligibility) -> str:
    inputs = (computed.get("line_12e") or {}).get("inputs") or {}
    if not any(key in inputs for key, _ in BOXES_12D):
        boxes = (eligibility or {}).get("age_blindness_boxes")
        return (f"<p><b>Line 12d boxes checked:</b> {int(boxes)}</p>" if boxes is not None else "")
    rows = "".join(
        f"<tr><td>{escape(label)}</td><td>{'Checked' if inputs.get(key) is True else 'Not checked'}</td></tr>"
        for key, label in BOXES_12D
    )
    count = sum(inputs.get(key) is True for key, _ in BOXES_12D)
    return (f"<h2>Line 12d: age and blindness boxes</h2><table><tr><th scope='col'>Box</th>"
            f"<th scope='col'>Status</th></tr>{rows}</table><p><b>Boxes checked:</b> {count} "
            f"(used for the standard deduction on line 12e)</p>")


def _dependents(facts) -> str:
    dependents = _fact(facts, "dependents") or []
    if not dependents:
        return ""
    rows = []
    for dep in dependents:
        ssn = str(dep.get("ssn", ""))
        shown = ("XXX-XX-" + ssn[-4:]) if is_fake_ssn(ssn) else "[not a valid test SSN]"
        rows.append(f"<tr><td>{escape(str(dep.get('name', '')))}</td>"
                    f"<td>{escape(str(dep.get('relationship', '')))}</td><td>{escape(shown)}</td></tr>")
    return ("<h2>Dependents</h2><table><tr><th scope='col'>Name</th><th scope='col'>Relationship</th>"
            "<th scope='col'>SSN</th></tr>" + "".join(rows) + "</table>")


def _review(review, history) -> str:
    if not review:
        return ""
    passed = review.get("verdict") == "pass"
    rounds = len(history or [])
    verdict = ("<span class='ok'>Passed</span>" if passed else "<span class='bad'>Did not pass</span>")
    note = (f" after {rounds} send-back round{'s' if rounds != 1 else ''} to Computation" if rounds
            else " with no send-backs")
    items = "".join(
        f"<li>Round {escape(str(r.get('round')))}: " + "; ".join(
            f"{escape(str(f.get('check')))} on {escape(str(f.get('line') or 'the return'))}: "
            f"{escape(str(f.get('issue')))}" for f in r.get("findings", [])) + "</li>"
        for r in history or [])
    still = "".join(f"<li>{escape(str(f.get('check')))} on {escape(str(f.get('line') or 'the return'))}: "
                    f"{escape(str(f.get('issue')))}</li>" for f in review.get("findings") or [])
    return (f"<h2>Review</h2><p>Independent check of every line against its source: {verdict}{note}.</p>"
            + (f"<p><b>Found and sent back:</b></p><ul>{items}</ul>" if items else "")
            + (f"<p><b>Open findings:</b></p><ul>{still}</ul>" if still else ""))


def _decisions(decisions) -> str:
    if not decisions:
        return ""
    rows = "".join(
        f"<tr><td>{escape(str(d.get('condition')))}</td><td>{escape(str(d.get('decision')))}</td>"
        f"<td>{escape(str(d.get('reviewer') or 'not named'))}</td>"
        f"<td>{escape(redact_pii(str(d.get('note') or '')))}</td></tr>" for d in decisions)
    return ("<h2>Volunteer decisions</h2><table><tr><th scope='col'>Reason for review</th>"
            "<th scope='col'>Decision</th><th scope='col'>Volunteer</th><th scope='col'>Note</th></tr>"
            + rows + "</table>")


def render_draft_html(computed: dict, facts: dict | None = None, eligibility: dict | None = None, *,
                      review: dict | None = None, review_history: list | None = None,
                      decisions: list | None = None, case_id: str | None = None) -> str:
    """Return a standalone HTML page. A line without a complete provenance record raises
    ValueError, so an unsourced amount can never be displayed. Everything but `computed` is
    optional context for the reviewer."""
    _check(computed)
    status, by = _status(facts, eligibility)
    body = []
    for title, rows in SECTIONS:
        lines = [_amount_row(num, label, computed[line]) for line, num, label in rows if line in computed]
        if lines:
            body.append(f"<h2>{escape(title)}</h2><table>{''.join(lines)}</table>")
    shown = {line for _, rows in SECTIONS for line, _, _ in rows}
    extra = [_amount_row(line, line, computed[line]) for line in sorted(computed) if line not in shown]
    if extra:
        body.append(f"<h2>Other lines</h2><table>{''.join(extra)}</table>")
    who = f" (from {escape(by)})" if by else ""
    case = f" &ndash; case {escape(case_id)}" if case_id else ""
    return (
        "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>DRAFT Form 1040-SR{' - ' + escape(case_id) if case_id else ''}</title>"
        f"<style>{STYLE}</style></head><body>"
        f"<h1>Form 1040-SR, tax year 2025{case}</h1>"
        "<p class='banner'><b>DRAFT, not filed.</b> Prepared for human review. "
        "Click any amount to see how it was produced.</p>"
        "<div><button type='button' id='open-all'>Show all sources</button>"
        "<button type='button' id='close-all'>Hide all sources</button>"
        "<button type='button' id='print'>Print</button></div>"
        f"<p><b>Filing status:</b> {escape(status)}{who}</p>"
        f"{_boxes_12d(computed, eligibility)}{_dependents(facts)}{''.join(body)}"
        f"{_review(review, review_history)}{_decisions(decisions)}"
        f"<script>{SCRIPT}</script></body></html>"
    )


def write_draft_form(state: dict, directory="output", name: str | None = None, audit=None,
                     actor: str = "system:draft_form"):
    """Render the draft from a final graph state and write it to `directory`. Returns the path.
    Raises ValueError when there are no computed lines or a line lacks provenance, so a draft
    with an unsourced amount is never written. Pass an `AuditLog` (src/audit.py) to record it."""
    computed = state.get("computed") or {}
    if not computed:
        raise ValueError("nothing computed yet, so there is no draft form to write")
    case_id = name or state.get("case_id") or "draft"
    html = render_draft_html(
        computed, state.get("facts"), state.get("eligibility"), review=state.get("review"),
        review_history=state.get("review_history"), decisions=state.get("human_decisions"),
        case_id=case_id)
    path = Path(directory) / f"{case_id}_1040sr.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    if audit is not None:
        audit.record(case_id, "draft_form_written", actor)
    return path
