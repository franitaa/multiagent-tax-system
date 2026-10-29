"""Write the sample DRAFT 1040-SR forms in demo/ (fake data only), each amount click-to-expand:

  demo/sample_1040sr.html       every income type, Schedule 1 and estimated payments
  demo/eval_case_1_1040sr.html  the clean run (docs/handoff-contract.md, scripts.run_scenarios clean)
  demo/eval_case_2_1040sr.html  the human-in-the-loop run: a spouse died in the tax year, a volunteer
                                resolves the filing status, then the draft is produced

Run from the project root:  python -m scripts.render_draft
Then open a file in a browser and click any amount.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from langgraph.types import Command  # noqa: E402

from src.agents import computation  # noqa: E402
from src.draft_form import render_draft_html, write_draft_form  # noqa: E402
from src.graph import build_graph  # noqa: E402
from src.orchestration.access import ToolBox  # noqa: E402
from src.scenarios import clean_case, spouse_died_case  # noqa: E402


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


def write_sample(out: Path) -> Path:
    computed = computation.run(sample_view, ToolBox("computation"))["computed"]
    path = out / "sample_1040sr.html"
    path.write_text(render_draft_html(computed, sample_view["facts"], {"filing_status": "single",
                    "age_blindness_boxes": 1}, case_id="sample"), encoding="utf-8")
    return path


def write_eval_cases(out: Path) -> list[Path]:
    paths = []
    with tempfile.TemporaryDirectory() as traces:
        graph = build_graph(trace_dir=traces)
        paths.append(write_draft_form(graph.invoke(clean_case(), {"configurable": {"thread_id": "eval1"}}),
                                      out, "eval_case_1"))

        case, agents = spouse_died_case()
        graph = build_graph(trace_dir=traces, agents=agents)
        config = {"configurable": {"thread_id": "eval2"}}
        graph.invoke(case, config)
        final = graph.invoke(Command(resume={
            "decision": "continue", "reviewer": "Demo Volunteer",
            "note": "demo: confirmed with the taxpayer that the spouse died in the tax year",
            "resolution": {"filing_status": "married_filing_jointly"}}), config)
        paths.append(write_draft_form(final, out, "eval_case_2"))
    return paths


if __name__ == "__main__":
    out = Path("demo")
    out.mkdir(exist_ok=True)
    for path in [write_sample(out), *write_eval_cases(out)]:
        print(f"Wrote {path.resolve()}")
