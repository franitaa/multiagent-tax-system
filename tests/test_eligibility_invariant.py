"""The orchestrator never ends a case "complete" without a filing status and an eligibility verdict."""
import json

import pytest
from langgraph.types import Command

from src import state as S
from src.graph import build_graph
from src.scenarios import clean_case, decided_rules
from tests.helpers import cfg, read_trace


def rules_returning(eligibility):
    return lambda view, tools: {"eligibility": eligibility,
                                "handoff_request": {"to": "computation", "reason": "test"}}


BROKEN = {
    "no filing status": {"in_scope": True, "filing_status": None, "citations": ["x"]},
    "empty filing status": {"in_scope": True, "filing_status": "", "citations": ["x"]},
    "no in_scope verdict": {"filing_status": "single"},
    "in_scope is not a boolean": {"in_scope": None, "filing_status": "single"},
    "Rules could not decide eligibility": {"in_scope": True, "filing_status": "single",
                                           "eligible_1040sr": None},
    "everything empty (what real Rules returns for facts it cannot read)": {
        "in_scope": True, "filing_status": None, "eligible_1040sr": None,
        "taxpayer_qualifies": None, "citations": []},
}


@pytest.mark.parametrize("eligibility", BROKEN.values(), ids=BROKEN.keys())
def test_an_undecided_return_pauses_for_a_human_and_never_completes(tmp_path, eligibility):
    graph = build_graph(trace_dir=tmp_path, agents={"rules": rules_returning(eligibility)})
    result = graph.invoke(clean_case(), cfg("undecided"))

    payload = result["__interrupt__"][0].value
    assert payload["condition"] == S.ELIGIBILITY_UNDECIDED and payload["raised_by"] == "orchestrator"
    assert payload["options"] == ["stop"]
    assert payload["reason"].startswith("Eligibility & Rules did not return")
    values = graph.get_state(cfg("undecided")).values
    assert values["status"] == S.AWAITING_HUMAN and not values.get("done")
    # caught right after Rules: nothing was computed or reviewed on an undecided status
    agents = [r["agent"] for r in read_trace(tmp_path, "undecided")]
    assert "computation" not in agents and "review" not in agents


def test_the_reason_names_exactly_what_is_missing(tmp_path):
    graph = build_graph(trace_dir=tmp_path, agents={"rules": rules_returning(
        {"in_scope": True, "filing_status": "single", "eligible_1040sr": None})})
    reason = graph.invoke(clean_case(), cfg("why"))["__interrupt__"][0].value["reason"]
    assert "eligible_1040sr" in reason and "filing_status" not in reason


def test_a_human_can_only_stop_and_the_case_ends_halted(tmp_path):
    graph = build_graph(trace_dir=tmp_path, agents={"rules": rules_returning(BROKEN["no filing status"])})
    graph.invoke(clean_case(), cfg("stop"))
    rejected = graph.invoke(Command(resume={"decision": "continue", "note": "ship it"}), cfg("stop"))
    assert "can only be stopped" in rejected["__interrupt__"][0].value["error"]
    final = graph.invoke(Command(resume={"decision": "stop", "note": "Rules could not read the answers"}),
                         cfg("stop"))
    assert final["status"] == S.HALTED_BY_HUMAN and final["done"] is True
    assert final["human_decisions"][0]["condition"] == S.ELIGIBILITY_UNDECIDED
    assert "computed" not in final or not final["computed"]


def test_the_trace_shows_why(tmp_path):
    graph = build_graph(trace_dir=tmp_path, agents={"rules": rules_returning(BROKEN["no filing status"])})
    graph.invoke(clean_case(), cfg("trace"))
    log = graph.get_state(cfg("trace")).values["handoff_log"]
    assert any(e["reason"] == "eligibility undecided: missing filing_status" for e in log)
    assert "Eligibility & Rules did not" not in (tmp_path / "trace.jsonl").read_text()  # no text in traces


def test_a_decided_return_still_completes(tmp_path):
    graph = build_graph(trace_dir=tmp_path, agents={"rules": decided_rules})
    result = graph.invoke(clean_case(), cfg("ok"))
    assert result["status"] == S.COMPLETE and "__interrupt__" not in result
    assert result["eligibility"]["filing_status"] == "single"


def test_not_eligible_for_the_1040sr_is_a_verdict_not_a_gap(tmp_path):
    graph = build_graph(trace_dir=tmp_path, agents={"rules": rules_returning(
        {"in_scope": True, "filing_status": "single", "eligible_1040sr": False, "citations": ["x"]})})
    result = graph.invoke(clean_case(), cfg("not-eligible"))
    assert "__interrupt__" not in result  # what Rules does with "not eligible" is Rules' call


def test_the_default_clean_run_is_unaffected(tmp_path):
    graph = build_graph(trace_dir=tmp_path)  # default agents, real Rules on main
    result = graph.invoke(clean_case(), cfg("default"))
    assert result["status"] == S.COMPLETE and result["eligibility"]["filing_status"]
    assert result["handoff_log"][-1]["reason"] == "review passed: draft ready"
