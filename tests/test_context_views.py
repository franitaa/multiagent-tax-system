"""Context strategy: scoped views, the Intake window, the rolling summary, the on/off flag."""
import json

import pytest

from src import state as S
from src.graph import build_graph
from src.orchestration.context import (
    MAX_INTAKE_MESSAGES, decision_inputs, summarise, view_for,
)
from src.scenarios import (
    clean_case, long_answer, long_document, long_session_agents, run_long_session, user,
)
from tests.helpers import cfg, read_trace


def full_state(**over):
    state = {
        "case_id": "c1",
        "messages": [user(f"message {i}") for i in range(20)],
        "facts": {"age": {"value": 70, "source": "user"},
                  "filing_status_claim": {"value": "single", "source": "user"},
                  "wages_claim": {"value": 1234.5, "source": "user"},
                  "has_dependent": {"value": True, "source": "user"}},
        "documents": [long_document("doc-1"), long_document("doc-2")],
        "extracted": {"doc-1": {"doc_id": "doc-1"}},
        "eligibility": {"in_scope": True, "filing_status": "single", "citations": ["x"]},
        "computed": {"line_1a": {"value": 1.0}},
        "session_summary": "intake complete (20 messages)",
        "escalation": {"pending": True, "condition": S.SOURCE_CONFLICT, "reason": "r", "raised_by": "rules"},
        "human_decisions": [],
    }
    return {**state, **over}


# ---- the view table ----------------------------------------------------------------------


def test_intake_sees_a_window_of_chat_plus_facts_and_summary_not_documents():
    view = view_for("intake", full_state())
    assert view["messages"] == full_state()["messages"][-MAX_INTAKE_MESSAGES:]
    assert set(view) == {"messages", "facts", "session_summary", "escalation", "human_decisions"}
    assert len(view["facts"]) == 4  # older chat is recalled through facts, in full


def test_rules_sees_facts_and_typed_records_but_no_chat_or_raw_documents():
    view = view_for("rules", full_state())
    assert set(view) == {"facts", "extracted", "session_summary", "escalation", "human_decisions"}


def test_computation_sees_numbers_and_filing_status_not_chat_or_free_text():
    view = view_for("computation", full_state())
    assert set(view["facts"]) == {"age", "wages_claim"}  # numeric only: not str, not bool
    assert view["eligibility"] == {"filing_status": "single"}
    assert "messages" not in view and "documents" not in view


def test_review_sees_the_assembled_return_not_chat_facts_or_documents():
    view = view_for("review", full_state())
    assert set(view) == {"computed", "eligibility", "session_summary", "escalation", "human_decisions"}
    assert view["eligibility"]["citations"] == ["x"]


def test_every_view_carries_the_escalation_flag():
    for agent in ("intake", "extraction", "rules", "computation", "review"):
        assert view_for(agent, full_state())["escalation"]["condition"] == S.SOURCE_CONFLICT


def test_orchestrator_view_has_no_documents_chat_or_fact_values():
    view = view_for("orchestrator", full_state())
    for forbidden in ("messages", "documents", "facts", "extracted", "computed", "review"):
        assert forbidden not in view
    assert view["n_messages"] == 20 and view["n_documents"] == 2


def test_flag_off_returns_the_full_state_to_every_agent():
    state = full_state()
    for agent in ("intake", "rules", "computation", "review"):
        view = view_for(agent, state, scoped=False)
        assert {"messages", "documents", "facts", "computed"} <= set(view)
        assert view["messages"] == state["messages"]  # nothing trimmed
    assert {"messages", "documents"} <= set(view_for("orchestrator", state, scoped=False))


# ---- the rolling summary -------------------------------------------------------------------


def test_summary_tracks_milestones_without_amounts_or_chat_text():
    state = full_state(escalation=None, review={"verdict": "pass"}, revision_count=1,
                       human_decisions=[{"condition": S.TAX_ADVICE_REQUEST, "decision": "continue",
                                         "note": "secret note text", "resolution": None}],
                       intake_complete=True, messages=[user("my SSN is 900-00-0000 and I earn $5,000")])
    text = summarise(decision_inputs(state))
    assert "intake complete (1 messages)" in text
    assert "documents extracted 1/2" in text and "eligibility: in scope" in text
    assert "review revision rounds: 1" in text and "review: pass" in text
    assert "human: TAX_ADVICE_REQUEST=continue" in text
    for leak in ("900-00-0000", "5,000", "$", "secret note text", "1234", "1.0"):
        assert leak not in text


def test_summary_is_bounded_however_long_the_session():
    many = [{"condition": S.SOURCE_CONFLICT, "decision": "continue", "note": "n", "resolution": None}] * 500
    short = summarise(decision_inputs(full_state()))
    long = summarise(decision_inputs(full_state(human_decisions=many, messages=[user("x")] * 5000)))
    assert len(long) < len(short) + 400  # only the last 5 human decisions are listed


def test_summary_reaches_the_agents_that_read_it(tmp_path):
    seen = {}

    def spy(name):
        from src.agents import AGENTS

        def run(view, tools):
            seen[name] = view.get("session_summary")
            return AGENTS[name](view, tools)

        return run

    graph = build_graph(trace_dir=tmp_path, agents={n: spy(n) for n in ("rules", "review")})
    graph.invoke(clean_case(), cfg("sum"))
    assert "documents extracted 1/1" in seen["rules"]
    assert "lines computed" in seen["review"] and "eligibility: in scope" in seen["review"]


# ---- both modes run the same scenario with the same outcome ---------------------------------


def run_both(tmp_path, turns, n_docs):
    out = {}
    for scoped in (True, False):
        graph = build_graph(trace_dir=tmp_path, context_strategy=scoped, agents=long_session_agents(turns))
        tid = f"{'on' if scoped else 'off'}-{turns}"
        out[scoped] = (run_long_session(graph, tid, turns, n_docs), read_trace(tmp_path, tid))
    return out


def test_both_modes_reach_the_same_outcome(tmp_path):
    out = run_both(tmp_path, turns=10, n_docs=4)
    (on, _), (off, _) = out[True], out[False]
    for key in ("status", "extracted", "computed", "facts", "revision_count", "review",
                "eligibility", "session_summary", "review_history"):
        assert on[key] == off[key], key
    assert on["status"] == S.COMPLETE and on["revision_count"] == 1


def test_with_the_strategy_on_intake_cost_grows_much_less_with_conversation_length(tmp_path):
    out = run_both(tmp_path, turns=30, n_docs=2)

    def intake(records):
        return [r["input_tokens"] for r in records if r["agent"] == "intake"]

    on, off = intake(out[True][1]), intake(out[False][1])
    assert len(on) == len(off) == 30
    on_growth, off_growth = on[-1] - on[0], off[-1] - off[0]
    assert off_growth > 4 * on_growth, (on_growth, off_growth)
    # the window really is capped: the chat part of the view stops growing after it fills
    assert on[-1] < off[-1] / 5
    # and every later agent is cheaper too
    for agent in ("extraction", "rules", "computation", "review"):
        s = [r["input_tokens"] for r in out[True][1] if r["agent"] == agent]
        f = [r["input_tokens"] for r in out[False][1] if r["agent"] == agent]
        assert max(s) < min(f), agent


def test_the_flag_is_recorded_in_the_trace(tmp_path):
    out = run_both(tmp_path, turns=3, n_docs=1)
    assert {r["context_mode"] for r in out[True][1]} == {"scoped"}
    assert {r["context_mode"] for r in out[False][1]} == {"full"}
