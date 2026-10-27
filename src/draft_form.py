"""Render a DRAFT Form 1040-SR page where every dollar amount expands (click, or keyboard) to show
its provenance: formula, inputs, source and tool. Plain HTML <details>; no dependencies.

The page is a draft for a human reviewer, never a filed return. Filing status, 12d box count and
dependents are shown for context; dependents' SSNs are masked and only valid 900-series test
numbers are displayed (security.is_fake_ssn)."""
from html import escape

from security import is_fake_ssn

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


def _money(value) -> str:
    return f"${value:,.2f}"


def _check(computed: dict) -> None:
    for line, record in computed.items():
        missing = REQUIRED - set(record)
        if missing:
            raise ValueError(f"{line} has no provenance for: {sorted(missing)}")


def _amount_row(num: str, label: str, record: dict) -> str:
    inputs = "".join(
        f"<li>{escape(str(k))}: {escape(str(v))}</li>" for k, v in record["inputs"].items()
    ) or "<li>(none)</li>"
    return (
        f"<tr><th scope='row'>{escape(num)}</th><td>{escape(label)}</td><td class='amt'>"
        f"<details><summary title='Click to see how this was produced'>"
        f"{_money(record['value'])}</summary>"
        f"<p><b>Formula:</b> {escape(record['formula'])}</p>"
        f"<p><b>Inputs:</b></p><ul>{inputs}</ul>"
        f"<p><b>Source:</b> {escape(record['source'])}</p>"
        f"<p><b>Tool:</b> {escape(record['tool'])}</p></details></td></tr>"
    )


def _fact(facts, name):
    item = (facts or {}).get(name)
    return item.get("value") if isinstance(item, dict) else None


def _header(facts, eligibility) -> str:
    status = ((eligibility or {}).get("filing_status") or _fact(facts, "filing_status")
              or "not yet determined")
    boxes = (eligibility or {}).get("age_blindness_boxes")
    parts = [f"<p><b>Filing status:</b> {escape(STATUS_LABELS.get(status, str(status)))}</p>"]
    if boxes is not None:
        parts.append(f"<p><b>Line 12d boxes checked (age 65+ / blind, you and spouse):</b> {int(boxes)}</p>")
    dependents = _fact(facts, "dependents") or []
    if dependents:
        rows = []
        for dep in dependents:
            ssn = str(dep.get("ssn", ""))
            shown = ("XXX-XX-" + ssn[-4:]) if is_fake_ssn(ssn) else "[not a valid test SSN]"
            rows.append(f"<tr><td>{escape(str(dep.get('name', '')))}</td>"
                        f"<td>{escape(str(dep.get('relationship', '')))}</td><td>{shown}</td></tr>")
        parts.append("<h2>Dependents</h2><table><tr><th>Name</th><th>Relationship</th><th>SSN</th></tr>"
                     + "".join(rows) + "</table>")
    return "".join(parts)


def render_draft_html(computed: dict, facts: dict | None = None, eligibility: dict | None = None) -> str:
    """Return a standalone HTML page. A line without a complete provenance record raises
    ValueError, so an unsourced amount can never be displayed. `facts` and `eligibility` are
    optional context (filing status, 12d boxes, dependents)."""
    _check(computed)
    body = []
    for title, rows in SECTIONS:
        lines = [_amount_row(num, label, computed[line]) for line, num, label in rows if line in computed]
        if lines:
            body.append(f"<h2>{escape(title)}</h2><table>{''.join(lines)}</table>")
    shown = {line for _, rows in SECTIONS for line, _, _ in rows}
    extra = [_amount_row(line, line, computed[line]) for line in sorted(computed) if line not in shown]
    if extra:
        body.append(f"<h2>Other lines</h2><table>{''.join(extra)}</table>")
    return (
        "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>DRAFT Form 1040-SR</title><style>"
        "body{font-family:Arial,sans-serif;font-size:1.15rem;max-width:52rem;margin:2rem auto;padding:0 1rem}"
        "table{width:100%;border-collapse:collapse;margin-bottom:1rem}"
        "th,td{border-bottom:1px solid #ccc;padding:.5rem;text-align:left}"
        "th[scope=row]{width:3.5rem}.amt{text-align:right;width:12rem}"
        "summary{cursor:pointer;color:#0645ad}details p,details ul{text-align:left;margin:.2rem 0}"
        ".banner{background:#fff3cd;border:1px solid #d6b656;padding:.6rem}"
        "</style></head><body><h1>Form 1040-SR, tax year 2025</h1>"
        "<p class='banner'><b>DRAFT, not filed.</b> Prepared for human review. "
        "Click any amount to see how it was produced.</p>"
        f"{_header(facts, eligibility)}{''.join(body)}</body></html>"
    )
