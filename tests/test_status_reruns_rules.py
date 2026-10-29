"""FILING_STATUS_AMBIGUITY: after the volunteer supplies the status, Rules decides again with it.

Rules raises the ambiguity itself (a spouse died in the tax year) and leaves a provisional
"undetermined" status. The router only runs Rules when there is no eligibility, so without the gate
clearing it a "continue" went on to Computation and the case stopped again as ELIGIBILITY_UNDECIDED
(eval case 2).
"""
from langgraph.types import Command

from src import state as S
from src.graph import build_graph
from src.scenarios import clean_case
from tests.helpers import cfg

FACTS = {
    "taxpayer_birth_date": "1950-02-02", "taxpayer_blind": "no", "married_dec31": "no",
    "household_situation": "widowed", "spouse_died_2025": "yes", "spouse_death_year": 2025,
}


def intake(view, tools):
    return {"facts": {k: {"value": v, "source": "user"} for k, v in FACTS.items()},
            "pending_question": None, "intake_complete": True,
            "handoff_request": {"to": "rules", "reason": "intake complete"}}


def test_the_volunteers_filing_status_reaches_the_draft(tmp_path):
    graph = build_graph(trace_dir=tmp_path, agents={"intake": intake})
    paused = graph.invoke(clean_case(turns=1), cfg("t"))
    assert paused["__interrupt__"][0].value["condition"] == S.FILING_STATUS_AMBIGUITY
    final = graph.invoke(
        Command(resume={"decision": "continue", "note": "confirmed with the taxpayer",
                        "resolution": {"filing_status": "married_filing_jointly"}}),
        cfg("t"),
    )
    assert "__interrupt__" not in final
    assert final["status"] == S.COMPLETE
    assert final["eligibility"]["filing_status"] == "married_filing_jointly"
