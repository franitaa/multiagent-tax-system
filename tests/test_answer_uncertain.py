"""ANSWER_UNCERTAIN: Rules cannot decide because a needed answer is "not_sure".

The whole path through the real graph, with the real Rules: Rules raises a real escalation
(a handoff_request alone is ignored by the router), the volunteer asks the taxpayer and resumes
with the corrected fact, and Rules decides again with it. Before the gate cleared `eligibility`,
a "continue" never re-ran Rules and a blind taxpayer finished with the provisional box count.
"""
import pytest
from langgraph.types import Command

from src import state as S
from src.graph import build_graph
from src.orchestration import human
from src.scenarios import clean_case
from tests.helpers import cfg


def intake_with(**answers):
    base = {"taxpayer_birth_date": "1950-03-04", "married_dec31": "no", "household_situation": "single"}
    facts = {k: {"value": v, "source": "user"} for k, v in {**base, **answers}.items()}

    def intake(view, tools):
        return {"facts": facts, "pending_question": None, "intake_complete": True,
                "handoff_request": {"to": "rules", "reason": "intake complete"}}
    return intake


def start(tmp_path, **answers):
    graph = build_graph(trace_dir=tmp_path, agents={"intake": intake_with(**answers)})
    return graph, graph.invoke(clean_case(turns=1), cfg("t"))


def volunteer(graph, resolution=None, note="asked the taxpayer on the phone", decision="continue"):
    answer = {"decision": decision, "note": note}
    if resolution is not None:
        answer["resolution"] = resolution
    return graph.invoke(Command(resume=answer), cfg("t"))


def pending(result):
    return result["__interrupt__"][0].value


JOINT = {"married_dec31": "yes", "file_jointly": "yes", "spouse_birth_date": "1951-05-06"}


# ---- it is a real, registered, continuable condition -----------------------------------------


def test_the_condition_is_registered_and_continuable():
    assert S.ANSWER_UNCERTAIN in S.ESCALATION_PRIORITY  # the runner's shape check needs this
    assert S.ANSWER_UNCERTAIN in S.AGENT_CONDITIONS
    assert S.ANSWER_UNCERTAIN in human.CONTINUABLE
    assert human.allowed_decisions(S.ANSWER_UNCERTAIN) == ("continue", "stop")


def test_a_not_sure_blindness_pauses_the_run_naming_the_fact(tmp_path):
    graph, result = start(tmp_path, taxpayer_blind="not_sure")
    payload = pending(result)
    assert payload["condition"] == S.ANSWER_UNCERTAIN
    assert payload["options"] == ["continue", "stop"]
    assert payload["resolution_fields"] == ["taxpayer_blind"]
    assert "taxpayer_blind" in payload["reason"]
    assert graph.get_state(cfg("t")).values.get("status") != S.COMPLETE


# ---- the volunteer's answer reaches Rules, which decides again -----------------------------------


@pytest.mark.parametrize("answer, boxes", [("yes", 2), ("no", 1)])
def test_the_taxpayers_blindness_answer_changes_the_boxes(tmp_path, answer, boxes):
    graph, _ = start(tmp_path, taxpayer_blind="not_sure")
    final = volunteer(graph, {"taxpayer_blind": answer})
    assert final["status"] == S.COMPLETE
    assert final["eligibility"]["age_blindness_boxes"] == boxes
    assert final["facts"]["taxpayer_blind"] == {"value": answer, "source": "human:ANSWER_UNCERTAIN"}
    assert final["human_decisions"][-1]["resolution"] == {"taxpayer_blind": answer}


@pytest.mark.parametrize("answer, boxes", [("yes", 3), ("no", 2)])
def test_the_spouses_blindness_answer_changes_the_boxes(tmp_path, answer, boxes):
    graph, result = start(tmp_path, spouse_blind="not_sure", **JOINT)
    assert pending(result)["resolution_fields"] == ["spouse_blind"]
    final = volunteer(graph, {"spouse_blind": answer})
    assert final["status"] == S.COMPLETE and final["eligibility"]["age_blindness_boxes"] == boxes


def test_a_not_sure_household_situation_is_resolved_into_a_filing_status(tmp_path):
    graph, result = start(tmp_path, household_situation="not_sure")
    assert pending(result)["resolution_fields"] == ["household_situation"]
    final = volunteer(graph, {"household_situation": "single"})
    assert final["status"] == S.COMPLETE and final["eligibility"]["filing_status"] == "single"


def test_a_not_sure_marital_status_is_resolved(tmp_path):
    graph, result = start(tmp_path, married_dec31="not_sure")
    assert pending(result)["resolution_fields"] == ["married_dec31"]
    final = volunteer(graph, {"married_dec31": "no"})
    assert final["status"] == S.COMPLETE and final["eligibility"]["filing_status"] == "single"


# ---- the gate does not let a bad answer through ---------------------------------------------------


@pytest.mark.parametrize("resolution", [
    None,                                  # continue without any corrected value
    {},                                    # same
    {"taxpayer_blind": "not_sure"},        # still unknown
    {"taxpayer_blind": "maybe"},           # not a valid answer (docs/answer-names.md)
    {"spouse_blind": "yes"},               # not the fact that is unresolved
    {"taxpayer_blind": "yes", "spouse_blind": "no"},   # more than the one unresolved fact
    {"taxpayer_blind": True},              # a bool is not "yes"
], ids=["none", "empty", "not-sure", "invalid-value", "wrong-fact", "extra-fact", "bool"])
def test_a_bad_resolution_keeps_the_case_with_the_volunteer(tmp_path, resolution):
    graph, _ = start(tmp_path, taxpayer_blind="not_sure")
    again = volunteer(graph, resolution)
    assert "__interrupt__" in again and pending(again).get("error"), "the gate must ask again"
    state = graph.get_state(cfg("t")).values
    assert state.get("status") != S.COMPLETE
    assert state["facts"]["taxpayer_blind"]["value"] == "not_sure"  # nothing was overwritten


def test_continue_still_needs_a_note(tmp_path):
    graph, _ = start(tmp_path, taxpayer_blind="not_sure")
    again = volunteer(graph, {"taxpayer_blind": "yes"}, note="")
    assert pending(again).get("error")


def test_a_bad_answer_followed_by_a_good_one_completes(tmp_path):
    graph, _ = start(tmp_path, taxpayer_blind="not_sure")
    volunteer(graph, {"taxpayer_blind": "maybe"})
    final = volunteer(graph, {"taxpayer_blind": "yes"})
    assert final["status"] == S.COMPLETE and final["eligibility"]["age_blindness_boxes"] == 2


def test_stop_ends_the_case_without_a_draft(tmp_path):
    graph, _ = start(tmp_path, taxpayer_blind="not_sure")
    final = volunteer(graph, decision="stop", note="")
    assert final["status"] == S.HALTED_BY_HUMAN and final["done"] is True
    assert not final.get("computed")
