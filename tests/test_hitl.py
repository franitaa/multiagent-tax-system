"""Human-in-the-loop: agents set a flag, the orchestrator interrupts, a human resumes."""
import json

import pytest
from langgraph.types import Command

from src import state as S
from src.agents import AGENTS
from src.graph import build_graph
from src.orchestration.human import CONTINUABLE
from src.scenarios import CONDITION_SOURCES, clean_case, escalation_case, raising, user

STOP_ONLY = sorted(set(CONDITION_SOURCES) - CONTINUABLE)
# ANSWER_UNCERTAIN is continuable too, but only with a corrected value for the fact Rules named, so
# the bare-note tests below do not apply; tests/test_answer_uncertain.py covers its whole path.
CONTINUE_OK = sorted(CONTINUABLE - {S.ANSWER_UNCERTAIN, S.INCOME_NOT_READ})  # the last: orchestrator-raised, see test_income_not_read.py


def cfg(tid):
    return {"configurable": {"thread_id": tid}}


def trace(tmp_path, tid):
    return [json.loads(x) for x in (tmp_path / f"{tid}.jsonl").read_text().splitlines()]


def answer(decision="continue", note="reviewed with the taxpayer (test)", **extra):
    return Command(resume={"decision": decision, "note": note, **extra})


def paused(tmp_path, condition, tid=None):
    graph = build_graph(trace_dir=tmp_path, agents=escalation_case(condition))
    result = graph.invoke(clean_case(), cfg(tid or condition))
    return graph, result


def test_rules_partition_the_conditions():
    assert set(CONTINUE_OK) == {S.SOURCE_CONFLICT, S.FILING_STATUS_AMBIGUITY, S.TAX_ADVICE_REQUEST}
    assert CONTINUABLE == set(CONTINUE_OK) | {S.ANSWER_UNCERTAIN, S.INCOME_NOT_READ}  # the last is orchestrator-raised
    assert set(STOP_ONLY) == {S.OUT_OF_SCOPE, S.FORM_1099R_BOX_2B, S.EXPLOITATION_SIGNS}


@pytest.mark.parametrize("condition", sorted(CONDITION_SOURCES))
def test_interrupt_payload_and_trace(tmp_path, condition):
    graph, result = paused(tmp_path, condition)
    payload = result["__interrupt__"][0].value
    assert payload["condition"] == condition
    assert payload["raised_by"] == CONDITION_SOURCES[condition][0]
    assert payload["options"] == (["continue", "stop"] if condition in CONTINUABLE else ["stop"])
    assert graph.get_state(cfg(condition)).values["status"] == S.AWAITING_HUMAN
    records = trace(tmp_path, condition)
    assert any(r.get("interrupted") and r["interrupted_on"] == condition for r in records)
    # personal-data guard: the free-text reason never reaches the trace
    assert "TEST:" not in (tmp_path / f"{condition}.jsonl").read_text()


@pytest.mark.parametrize("condition", CONTINUE_OK)
def test_continue_with_note_resumes_and_is_audited(tmp_path, condition):
    graph, _ = paused(tmp_path, condition)
    final = graph.invoke(answer("continue", "volunteer confirmed with taxpayer"), cfg(condition))
    assert final["status"] == S.COMPLETE and final["escalation"] is None
    decision = final["human_decisions"][0]
    assert decision == {"condition": condition, "decision": "continue",
                        "note": "volunteer confirmed with taxpayer", "resolution": None}


def re_asked(graph, tid, command, match):
    """A rejected answer returns a fresh interrupt carrying an error; nothing is applied."""
    result = graph.invoke(command, cfg(tid))
    payload = result["__interrupt__"][0].value
    assert match in payload["error"]
    values = graph.get_state(cfg(tid)).values
    assert values["status"] == S.AWAITING_HUMAN and not values.get("human_decisions")
    return payload


@pytest.mark.parametrize("condition", CONTINUE_OK)
@pytest.mark.parametrize("note", ["", "   ", None])
def test_continue_with_empty_note_is_rejected_then_corrected(tmp_path, condition, note):
    graph, _ = paused(tmp_path, condition)
    re_asked(graph, condition, Command(resume={"decision": "continue", "note": note}), "non-empty note")
    final = graph.invoke(answer("continue", "now with a note"), cfg(condition))
    assert final["status"] == S.COMPLETE
    assert final["human_decisions"][0]["note"] == "now with a note"


@pytest.mark.parametrize("condition", STOP_ONLY)
def test_continue_is_rejected_for_stop_only_conditions(tmp_path, condition):
    graph, _ = paused(tmp_path, condition)
    payload = re_asked(graph, condition, answer("continue", "I take responsibility"), "can only be stopped")
    assert payload["options"] == ["stop"]
    final = graph.invoke(answer("stop"), cfg(condition))  # and stop still works afterwards
    assert final["status"] == S.HALTED_BY_HUMAN


@pytest.mark.parametrize("condition", sorted(CONDITION_SOURCES))
def test_stop_halts_and_runs_no_more_agents(tmp_path, condition):
    graph, _ = paused(tmp_path, condition)
    final = graph.invoke(answer("stop", note=""), cfg(condition))  # note optional for stop

    assert final["status"] == S.HALTED_BY_HUMAN and final["done"] is True
    assert final["human_decisions"][0]["decision"] == "stop"
    records = trace(tmp_path, condition)
    last_human = max(i for i, r in enumerate(records) if r["agent"] == "human")
    assert {r["agent"] for r in records[last_human + 1:]} <= {"orchestrator"}


def test_filing_status_resolution_is_stored_as_a_sourced_fact(tmp_path):
    graph, _ = paused(tmp_path, S.FILING_STATUS_AMBIGUITY)
    final = graph.invoke(
        answer("continue", "spouse died in 2025; surviving spouse rules checked with volunteer lead",
               resolution={"filing_status": "married_filing_jointly"}),
        cfg(S.FILING_STATUS_AMBIGUITY),
    )
    assert final["facts"]["filing_status"] == {
        "value": "married_filing_jointly", "source": "human:FILING_STATUS_AMBIGUITY"}
    assert final["human_decisions"][0]["resolution"] == {"filing_status": "married_filing_jointly"}


def test_source_conflict_resolution_sets_named_facts(tmp_path):
    graph, _ = paused(tmp_path, S.SOURCE_CONFLICT)
    final = graph.invoke(
        answer("continue", "taxpayer confirmed the document is right", resolution={"has_interest": True}),
        cfg(S.SOURCE_CONFLICT),
    )
    assert final["facts"]["has_interest"] == {"value": True, "source": "human:SOURCE_CONFLICT"}


@pytest.mark.parametrize("condition,resolution", [
    (S.FILING_STATUS_AMBIGUITY, {"filing_status": "widowed"}),      # not a real status
    (S.FILING_STATUS_AMBIGUITY, {"filing_status": "single", "x": 1}),  # extra key
    (S.TAX_ADVICE_REQUEST, {"anything": 1}),                         # nothing to resolve
    (S.SOURCE_CONFLICT, {"": 1}),                                    # bad fact name
    (S.SOURCE_CONFLICT, {"k": {"nested": 1}}),                       # not a scalar
])
def test_bad_resolutions_are_rejected(tmp_path, condition, resolution):
    graph, _ = paused(tmp_path, condition)
    re_asked(graph, condition, answer("continue", "n", resolution=resolution), "")


def test_resolution_with_stop_is_rejected(tmp_path):
    graph, _ = paused(tmp_path, S.SOURCE_CONFLICT)
    re_asked(graph, "SOURCE_CONFLICT", answer("stop", "n", resolution={"a": 1}), "only applies to 'continue'")


@pytest.mark.parametrize("bad", [{"decision": "approve"}, "continue", {"note": "x"}, 5])
def test_malformed_resume_values_are_rejected(tmp_path, bad):
    graph, _ = paused(tmp_path, S.TAX_ADVICE_REQUEST)
    re_asked(graph, S.TAX_ADVICE_REQUEST, Command(resume=bad), "")
    assert graph.invoke(answer("continue", "ok"), cfg(S.TAX_ADVICE_REQUEST))["status"] == S.COMPLETE


def test_out_of_scope_without_a_flag_is_caught_by_the_router(tmp_path):
    out_of_scope = lambda view, tools: {"eligibility": {"in_scope": False, "citations": ["x"]}}
    graph = build_graph(trace_dir=tmp_path, agents={"rules": out_of_scope})
    result = graph.invoke(clean_case(), cfg("oos"))
    payload = result["__interrupt__"][0].value
    assert payload["condition"] == S.OUT_OF_SCOPE and payload["raised_by"] == "orchestrator"
    assert payload["options"] == ["stop"]
    final = graph.invoke(answer("stop"), cfg("oos"))
    assert final["status"] == S.HALTED_BY_HUMAN


def test_interrupt_in_the_middle_of_a_conversation(tmp_path):
    two_turns = lambda view: sum(m["role"] == "user" for m in view["messages"]) >= 2
    agents = {"intake": raising(AGENTS["intake"], "intake", S.TAX_ADVICE_REQUEST, "TEST", two_turns)}
    graph = build_graph(trace_dir=tmp_path, agents=agents)
    config = cfg("mid")

    first = graph.invoke(clean_case(turns=1), config)
    assert first["status"] == S.AWAITING_USER and "__interrupt__" not in first

    second = graph.invoke({"messages": [user("Should I itemize?")]}, config)
    assert second["__interrupt__"][0].value["condition"] == S.TAX_ADVICE_REQUEST

    final = graph.invoke(answer("continue", "question noted for the volunteer"), config)
    assert final["status"] == S.COMPLETE
    assert [m["role"] for m in final["messages"]].count("user") == 2
