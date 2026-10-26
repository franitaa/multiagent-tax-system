"""Loop guard: pathological handoff cycles escalate to a human; legitimate flows do not trip it."""
import pytest
from langgraph.types import Command

from src import state as S
from src.agents import AGENTS
from src.graph import build_graph
from src.orchestration.context import routing_view
from src.orchestration.guard import MAX_CONSECUTIVE, MAX_SEEN, apply_guard, fingerprint
from src.orchestration.router import Route
from src.scenarios import clean_case, raising, user
from tests.helpers import cfg
from tests.test_review_loop import Scripted, value_at_least


def guard_reasons(result_or_state):
    return [e["reason"] for e in result_or_state["handoff_log"] if e["reason"].startswith("loop guard")]


class Counting:
    """Wrap an agent so a test can count how often it was called."""

    def __init__(self, fn):
        self.fn, self.calls = fn, 0

    def __call__(self, view, tools):
        self.calls += 1
        return self.fn(view, tools)


# ---- it triggers -------------------------------------------------------------------------


@pytest.mark.parametrize("agent", ["intake", "extraction", "rules", "computation", "review"])
def test_an_agent_that_keeps_returning_empty_output_trips_the_guard(tmp_path, agent):
    empty = Counting(lambda view, tools: {})
    graph = build_graph(trace_dir=tmp_path, agents={agent: empty})
    result = graph.invoke(clean_case(), cfg(f"empty-{agent}"))

    payload = result["__interrupt__"][0].value
    assert payload["condition"] == S.LOOP_GUARD and payload["raised_by"] == "orchestrator"
    assert payload["options"] == ["stop"]
    assert empty.calls <= 2, "the guard must stop it after one wasted call, not run to the recursion limit"

    values = graph.get_state(cfg(f"empty-{agent}")).values
    assert any("no progress" in r for r in guard_reasons(values))

    rejected = graph.invoke(Command(resume={"decision": "continue", "note": "retry"}), cfg(f"empty-{agent}"))
    assert "can only be stopped" in rejected["__interrupt__"][0].value["error"]
    final = graph.invoke(Command(resume={"decision": "stop", "note": ""}), cfg(f"empty-{agent}"))
    assert final["status"] == S.HALTED_BY_HUMAN and empty.calls <= 2


def test_same_hop_repeating_while_state_keeps_changing_trips_the_guard(tmp_path):
    def chatty(view, tools):  # changes state every call (a new message) but never finishes
        return {"messages": [{"role": "assistant", "content": "still thinking"}]}

    chatty = Counting(chatty)
    graph = build_graph(trace_dir=tmp_path, agents={"intake": chatty})
    result = graph.invoke(clean_case(), cfg("chatty"))

    assert result["__interrupt__"][0].value["condition"] == S.LOOP_GUARD
    assert chatty.calls == MAX_CONSECUTIVE  # the next dispatch is refused
    reasons = guard_reasons(graph.get_state(cfg("chatty")).values)
    assert reasons and "in a row" in reasons[0]


# ---- it does NOT trigger on legitimate flows ----------------------------------------------


@pytest.mark.parametrize("n_docs", [1, 4, 12])
def test_clean_run_does_not_trip_the_guard(tmp_path, n_docs):
    graph = build_graph(trace_dir=tmp_path)
    result = graph.invoke(clean_case(n_docs=n_docs), cfg(f"clean{n_docs}"))
    assert result["status"] == S.COMPLETE and "__interrupt__" not in result
    assert guard_reasons(result) == []


def test_waiting_for_the_taxpayer_repeatedly_does_not_trip_the_guard(tmp_path):
    graph = build_graph(trace_dir=tmp_path)
    config = cfg("waiting")
    graph.invoke(clean_case(turns=1), config)
    for _ in range(5):  # a UI re-polling with no new message
        again = graph.invoke({}, config)
        assert again["status"] == S.AWAITING_USER
    final = graph.invoke({"messages": [user("I am 70, single, with one W-2.")]}, config)
    assert final["status"] == S.COMPLETE and guard_reasons(final) == []


def test_a_human_round_trip_does_not_trip_the_guard(tmp_path):
    agents = {"intake": raising(AGENTS["intake"], "intake", S.TAX_ADVICE_REQUEST, "TEST")}
    graph = build_graph(trace_dir=tmp_path, agents=agents)
    graph.invoke(clean_case(), cfg("human"))
    final = graph.invoke(Command(resume={"decision": "continue", "note": "noted"}), cfg("human"))
    assert final["status"] == S.COMPLETE and guard_reasons(final) == []


def test_a_full_three_round_review_loop_does_not_trip_the_guard(tmp_path):
    script = Scripted(value_at_least(4000))  # fails 3 times, passes on the 4th look
    graph = build_graph(trace_dir=tmp_path, agents=script.agents())
    result = graph.invoke(clean_case(), cfg("three-rounds"))

    assert result["status"] == S.COMPLETE and "__interrupt__" not in result
    assert result["revision_count"] == 3 and len(script.review_views) == 4
    assert guard_reasons(result) == []


def test_an_exhausted_review_loop_reports_the_bound_not_the_guard(tmp_path):
    script = Scripted(lambda view: False)
    graph = build_graph(trace_dir=tmp_path, agents=script.agents())
    result = graph.invoke(clean_case(), cfg("exhausted"))
    assert result["__interrupt__"][0].value["condition"] == S.REVIEW_BOUND_EXCEEDED
    assert guard_reasons(graph.get_state(cfg("exhausted")).values) == []


# ---- the pure pieces -------------------------------------------------------------------


def base_view(**over):
    state = {"messages": [user("a")], "intake_complete": True}
    return {**routing_view(state), **over}


def test_fingerprint_ignores_counters_and_logs_but_sees_progress():
    a = base_view()
    assert fingerprint(a) == fingerprint({**a, "step": 99, "status": "x", "last_handoffs": [1, 2]})
    assert fingerprint(a) != fingerprint({**a, "has_eligibility": True})
    assert fingerprint(a) != fingerprint({**a, "revision_count": 1})


def test_apply_guard_resets_history_when_the_call_ends_or_hands_to_a_human():
    view = base_view(guard={"seen": ["abc"], "last": "intake", "streak": 2})
    for target in (S.END_KEY, S.HUMAN_KEY):
        assert apply_guard(view, Route(target, "r")).update["guard"] == {}


def test_apply_guard_records_dispatches_and_caps_the_history():
    view = base_view(guard={"seen": [f"{i:08x}" for i in range(MAX_SEEN)], "last": "rules", "streak": 1})
    out = apply_guard(view, Route("intake", "r"))
    assert out.next == "intake" and len(out.update["guard"]["seen"]) == MAX_SEEN
    assert out.update["guard"]["seen"][-1] == fingerprint(view)
    assert out.update["guard"]["streak"] == 1  # different agent from last time


def test_apply_guard_trip_replaces_the_decision_and_discards_its_update():
    view = base_view()
    view["guard"] = {"seen": [fingerprint(view)], "last": "intake", "streak": 1}
    out = apply_guard(view, Route("intake", "r", {"revision_count": 9}))
    assert out.next == S.HUMAN_KEY and "revision_count" not in out.update
    assert out.update["escalation"]["condition"] == S.LOOP_GUARD
    assert out.update["status"] == S.AWAITING_HUMAN
