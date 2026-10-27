"""Render the computed lines as a DRAFT Form 1040-SR page where every amount can be expanded
to show its provenance (formula, inputs, source, tool). Plain HTML <details>; no dependencies.
Output is a draft for a human reviewer, never a filed return."""
from html import escape

LINE_LABELS = {
    "line_1a": "1a  Wages from Form(s) W-2",
    "line_2b": "2b  Taxable interest",
    "line_3b": "3b  Ordinary dividends",
    "line_4b": "4b  IRA distributions (taxable)",
    "line_5b": "5b  Pensions and annuities (taxable)",
    "line_6a": "6a  Social Security benefits",
    "line_6b": "6b  Taxable Social Security benefits",
    "line_9": "9   Total income",
    "line_10": "10  Adjustments to income (Schedule 1)",
    "line_11": "11  Adjusted gross income (AGI)",
    "line_12e": "12e Standard deduction (with age/blindness additions)",
    "line_13b": "13b Additional deductions (Schedule 1-A senior deduction)",
    "line_14": "14  Total deductions",
    "line_15": "15  Taxable income",
    "line_16": "16  Tax",
    "line_17": "17  Amount from Schedule 2, part I",
    "line_18": "18  Add lines 16 and 17",
    "line_20": "20  Amount from Schedule 3 (nonrefundable credits)",
    "line_22": "22  Tax after credits",
    "line_23": "23  Other taxes (Schedule 2)",
    "line_24": "24  Total tax",
    "line_25a": "25a Federal tax withheld",
    "line_26": "26  Estimated tax payments",
    "line_31": "31  Amount from Schedule 3 (other payments)",
    "line_33": "33  Total payments",
    "line_34": "34  Overpaid (refund)",
    "line_37": "37  Amount you owe",
}


def _sort_key(line: str):
    digits = "".join(c for c in line.removeprefix("line_") if c.isdigit())
    return int(digits or 0), line


def _money(value) -> str:
    return f"${value:,.2f}"


def render_draft_html(computed: dict) -> str:
    """Return a standalone HTML page. A line without a complete provenance record raises
    ValueError, so an unsourced amount can never be displayed."""
    rows = []
    for line in sorted(computed, key=_sort_key):
        record = computed[line]
        missing = {"value", "formula", "inputs", "source", "tool"} - set(record)
        if missing:
            raise ValueError(f"{line} has no provenance for: {sorted(missing)}")
        inputs = "".join(
            f"<li>{escape(str(k))}: {escape(str(v))}</li>" for k, v in record["inputs"].items()
        ) or "<li>(none)</li>"
        rows.append(
            f"<tr><td>{escape(LINE_LABELS.get(line, line))}</td><td class='amt'>"
            f"<details><summary title='Click to see how this was produced'>"
            f"{_money(record['value'])}</summary>"
            f"<p><b>Formula:</b> {escape(record['formula'])}</p>"
            f"<p><b>Inputs:</b></p><ul>{inputs}</ul>"
            f"<p><b>Source:</b> {escape(record['source'])}</p>"
            f"<p><b>Tool:</b> {escape(record['tool'])}</p></details></td></tr>"
        )
    return (
        "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
        "<title>DRAFT Form 1040-SR</title><style>"
        "body{font-family:sans-serif;max-width:50rem;margin:2rem auto}"
        "td{border-bottom:1px solid #ccc;padding:.4rem}.amt{text-align:right}"
        "summary{cursor:pointer;color:#0645ad}details p,details ul{text-align:left;margin:.2rem 0}"
        "</style></head><body><h1>DRAFT Form 1040-SR (not filed)</h1>"
        "<p>Prepared for human review. Click any amount to see how it was produced.</p>"
        f"<table>{''.join(rows)}</table></body></html>"
    )
