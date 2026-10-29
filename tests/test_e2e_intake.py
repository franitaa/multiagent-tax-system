"""The real Intake (feature/intake-agent) driven end to end through our graph.

The real Intake driving the real Rules through our graph (docs/intake-rules-contract.md). The
gaps these tests once documented as strict expected failures were closed by the Rules rework.
"""
import json

import pytest

from src import state as S
from src.graph import build_graph
from tests.helpers import cfg, read_trace
from tests.interview import resume, start_interview

intake_agent = pytest.importorskip(
    "src.agents.intake_agent", reason="Intake (feature/intake-agent) is not merged yet")


def finished_or_paused_undecided(result):
    """With today's Rules the real Intake's answers leave eligibility undecided, and the orchestrator
    must pause for a human instead of ending "complete". Once Rules reads Intake's names this is a
    plain complete run. Either way, a run never ends complete with an empty filing status."""
    if "__interrupt__" in result:
        payload = result["__interrupt__"][0].value
        assert payload["condition"] == S.ELIGIBILITY_UNDECIDED and payload["options"] == ["stop"]
    else:
        assert result["status"] == S.COMPLETE and result["eligibility"]["filing_status"]


def graph_with_real_intake(tmp_path):
    return build_graph(trace_dir=tmp_path, agents={"intake": intake_agent.run})


def test_real_intake_finishes_a_single_filer_interview(tmp_path):
    graph = graph_with_real_intake(tmp_path)
    result, asked = start_interview(graph, cfg("e2e-single"))

    assert result["intake_complete"] is True
    finished_or_paused_undecided(result)
    assert asked > 15  # a real interview, one graph call per answer
    # far longer than Intake's 6-message window, and it still worked: it keeps its place in facts
    assert len(result["messages"]) > 2 * 6
    assert "intake_progress" in result["facts"]
    assert all(set(f) >= {"value", "source"} for f in result["facts"].values())
    records = read_trace(tmp_path, "e2e-single")
    assert all(r["violations"] == [] for r in records)  # never wrote outside its allow-list
    intake_reads = {f for r in records if r["agent"] == "intake" for f in r["fields_read"]}
    assert intake_reads <= {"messages", "facts", "session_summary", "escalation", "human_decisions"}


def test_real_intake_escalates_when_a_spouse_died_and_the_interview_resumes(tmp_path):
    graph = graph_with_real_intake(tmp_path)
    overrides = {"spouse pass away": "yes"}
    paused, _ = start_interview(graph, cfg("e2e-spouse"), overrides)

    payload = paused["__interrupt__"][0].value
    assert payload["condition"] == S.FILING_STATUS_AMBIGUITY and payload["raised_by"] == "intake"
    assert payload["options"] == ["continue", "stop"]

    after = resume(graph, cfg("e2e-spouse"), "continue",
                   "volunteer confirmed with the taxpayer (test)",
                   resolution={"filing_status": "married_filing_jointly"})
    from tests.interview import finish_interview
    final, _ = finish_interview(graph, cfg("e2e-spouse"), after, overrides)

    finished_or_paused_undecided(final)
    assert final["facts"]["filing_status"] == {
        "value": "married_filing_jointly", "source": "human:FILING_STATUS_AMBIGUITY"}
    assert [d["condition"] for d in final["human_decisions"]] == [S.FILING_STATUS_AMBIGUITY]


def test_rules_decides_eligibility_and_status_from_real_intake_facts(tmp_path):
    graph = graph_with_real_intake(tmp_path)
    result, _ = start_interview(graph, cfg("e2e-rules"))
    assert result["eligibility"]["eligible_1040sr"] is True
    assert result["eligibility"]["filing_status"] == "single"


SCREENING = {  # question text -> fact name Intake records it under (docs/intake-script.md Q17a-e)
    "sell any stocks": "sold_stocks_or_property",
    "own business": "business_or_rental_income",
    "outside the united states": "foreign_income_or_accounts",
    "digital assets": "digital_assets",
    "other tax forms": "has_other_tax_forms",
}


@pytest.mark.parametrize("question", SCREENING, ids=SCREENING.values())
def test_an_out_of_scope_screening_answer_escalates_as_out_of_scope(tmp_path, question):
    graph = graph_with_real_intake(tmp_path)
    result, _ = start_interview(graph, cfg("e2e-scope"), {question: "yes"})
    assert "__interrupt__" in result, "a case with an out-of-scope item must not complete"
    assert result["__interrupt__"][0].value["condition"] == S.OUT_OF_SCOPE
