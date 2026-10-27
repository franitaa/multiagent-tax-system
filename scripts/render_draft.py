"""Write a sample DRAFT 1040-SR with click-to-expand provenance (fake data only).

Run from the project root:  python scripts/render_draft.py
Then open demo/sample_1040sr.html in a browser and click any amount.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agents import computation  # noqa: E402
from src.draft_form import render_draft_html  # noqa: E402
from src.orchestration.access import ToolBox  # noqa: E402


def doc(kind, **fields):
    return {"kind": kind, "fields": {k: {"value": v, "source": "sample"} for k, v in fields.items()}}


sample_view = {
    "facts": {k: {"value": v, "source": "user"} for k, v in {
        "married_dec31": "no", "household_situation": "single",
        "taxpayer_birth_date": "1952-06-15", "taxpayer_blind": "no",
        "estimated_payments_amount": 1200,
        "dependents": [{"name": "Sample Grandchild", "relationship": "grandchild",
                        "ssn": "912-34-5678"}],
    }.items()},
    "extracted": {
        "doc-1": doc("W-2", box_1=28000, box_2=2600),
        "doc-2": doc("SSA-1099", box_5=18000),
        "doc-3": doc("1099-INT", box_1=150, box_8=40),
        "doc-4": doc("1099-DIV", box_1a=300, box_1b=200),
    },
    "eligibility": {},
}

if __name__ == "__main__":
    computed = computation.run(sample_view, ToolBox("computation"))["computed"]
    out = Path("demo/sample_1040sr.html")
    out.parent.mkdir(exist_ok=True)
    out.write_text(render_draft_html(computed, sample_view["facts"], {"filing_status": "single",
                   "age_blindness_boxes": 1}), encoding="utf-8")
    print(f"Wrote {out.resolve()}")
