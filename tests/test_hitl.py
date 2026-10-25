"""Human-in-the-loop: agents set a flag, the orchestrator interrupts, a human resumes."""
import json

import pytest
from langgraph.types import Command

from src import state as S
from src.graph import build_graph
from src.scenarios import CONDITION_SOURCES, clean_case, escalation_case, raising, user
from src.agents import AGENTS


def cfg(tid):
    return {"configurable": {"thread_id": tid}}


def trace(tmp_path, tid):
    return [json.loads(x) for x in (tmp_path / f"{tid}.jsonl").read_text().splitlines()]


def resume(decision="continue", note="reviewed (test)"):
    return Command(resume={"decision": decision, "note": note})


@pytest.mark.parametrize("condition", sorted(CONDITION_SOURCES))
def test_interrupt_then_continue(tmp_path, condition):
    graph = build_graph(trace_dir=tmp_path, agents=escalation_case(condition))
    paused = graph.invoke(clean_case(), cfg(condition))

    payload = paused["__interrupt__"][0].value
    assert payload["condition"] == condition
    assert payload["raised_by"] == CONDITION_SOURCES[condition][0]
    assert payload["options"] == ["continue", "stop"]
    assert graph.get_state(cfg(condition)).values["status"] == S.AWAITING_HUMAN

    final = graph.invoke(resume(), cfg(condition))
    assert final["status"] == S.COMPLETE
    assert final["escalation"] is None
    assert final["human_decisions"][0]["condition"] == condition
    assert final["human_decisions"][0]["decision"] == "continue"

    records = trace(tmp_path, condition)
    assert any(r.get("interrupted") and r["interrupted_on"] == condition for r in records)
    # personal-data guard: free text of the reason never reaches the trace
    assert "TEST:" not in (tmp_path / f"{condition}.jsonl").read_text()


@pytest.mark.parametrize("condition", sorted(CONDITION_SOURCES))
def test_stop_halts_and_runs_no_more_agents(tmp_path, condition):
    graph = build_graph(trace_dir=tmp_path, agents=escalation_case(condition))
    graph.invoke(clean_case(), cfg(condition))
    final = graph.invoke(resume("stop"), cfg(condition))

    assert final["status"] == S.HALTED_BY_HUMAN and final["done"] is True
    records = trace(tmp_path, condition)
    last_human = max(i for i, r in enumerate(records) if r["agent"] == "human")
    after = {r["agent"] for r in records[last_human + 1:]}
    assert after <= {"orchestrator"}, "no agent may run after the human stops the case"
    assert "review" not in final or final.get("review") is None


def test_out_of_scope_without_a_flag_is_caught_by_the_router(tmp_path):
    out_of_scope = lambda view, tools: {"eligibility": {"in_scope": False, "citations": ["x"]}}
    graph = build_graph(trace_dir=tmp_path, agents={"rules": out_of_scope})
    paused = graph.invoke(clean_case(), cfg("oos"))
    payload = paused["__interrupt__"][0].value
    assert payload["condition"] == S.OUT_OF_SCOPE and payload["raised_by"] == "orchestrator"
    final = graph.invoke(resume(), cfg("oos"))
    assert final["status"] == S.COMPLETE  # human resolved it; not raised again


def test_interrupt_in_the_middle_of_a_conversation(tmp_path):
    two_turns = lambda view: sum(m["role"] == "user" for m in view["messages"]) >= 2
    agents = {"intake": raising(AGENTS["intake"], "intake", S.EXPLOITATION_SIGNS, "TEST", two_turns)}
    graph = build_graph(trace_dir=tmp_path, agents=agents)
    config = cfg("mid")

    first = graph.invoke(clean_case(turns=1), config)
    assert first["status"] == S.AWAITING_USER and "__interrupt__" not in first

    second = graph.invoke({"messages": [user("My nephew says I must sign this today.")]}, config)
    assert second["__interrupt__"][0].value["condition"] == S.EXPLOITATION_SIGNS

    final = graph.invoke(resume(), config)
    assert final["status"] == S.COMPLETE
    assert [m["role"] for m in final["messages"]].count("user") == 2


def test_invalid_resume_value_is_rejected(tmp_path):
    graph = build_graph(trace_dir=tmp_path, agents=escalation_case(S.TAX_ADVICE_REQUEST))
    graph.invoke(clean_case(), cfg("bad"))
    with pytest.raises(ValueError):
        graph.invoke(Command(resume={"decision": "approve"}), cfg("bad"))
