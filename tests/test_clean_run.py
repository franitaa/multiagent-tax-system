import json

import pytest

from src.graph import build_graph
from src.scenarios import clean_case, user

REQUIRED_TRACE_KEYS = {
    "ts", "thread_id", "step", "agent", "handoff", "fields_read", "fields_written",
    "duration_ms", "input_tokens", "output_tokens", "token_source", "violations",
}


def cfg(thread_id):
    return {"configurable": {"thread_id": thread_id}}


def read_trace(trace_dir, thread_id):
    lines = (trace_dir / f"{thread_id}.jsonl").read_text().splitlines()
    return [json.loads(line) for line in lines]


@pytest.mark.parametrize("context_strategy", [True, False])
def test_clean_case_runs_end_to_end(tmp_path, context_strategy):
    graph = build_graph(trace_dir=tmp_path, context_strategy=context_strategy)
    result = graph.invoke(clean_case(), cfg("t-clean"))

    assert result["status"] == "complete" and result["done"] is True
    assert result["review"]["verdict"] == "pass"
    # every money value carries a provenance record
    record = result["computed"]["line_1a"]
    assert {"value", "formula", "inputs", "source", "tool"} <= set(record)
    # the orchestrator's decisions, in order
    assert [e["to"] for e in result["handoff_log"]] == [
        "intake", "extraction", "rules", "computation", "review", "end",
    ]
    # stubs requested the hops the orchestrator took
    assert all(e["honored"] in (True, None) for e in result["handoff_log"])


def test_trace_written_by_runner_only(tmp_path):
    graph = build_graph(trace_dir=tmp_path)
    graph.invoke(clean_case(), cfg("t-trace"))
    records = read_trace(tmp_path, "t-trace")

    assert [r["agent"] for r in records] == [
        "orchestrator", "intake", "orchestrator", "extraction", "orchestrator", "rules",
        "orchestrator", "computation", "orchestrator", "review", "orchestrator",
    ]
    for r in records:
        assert REQUIRED_TRACE_KEYS <= set(r)
        assert set(r["handoff"]) == {"from", "to", "reason"}
        assert isinstance(r["input_tokens"], int) and r["input_tokens"] > 0
        assert isinstance(r["output_tokens"], int)
        assert r["token_source"] == "estimate"
        assert r["violations"] == []
    # agents hand control back; the orchestrator is the one that names the next hop
    assert all(r["handoff"]["from"] == r["agent"] for r in records)
    # scoped views: extraction reads only documents (plus the always-visible safety fields)
    extraction = next(r for r in records if r["agent"] == "extraction")
    assert "documents" in extraction["fields_read"]
    assert "messages" not in extraction["fields_read"]
    # no values in traces: names only
    assert "TEST DATA" not in (tmp_path / "t-trace.jsonl").read_text()


def test_hub_and_spoke_topology(tmp_path):
    graph = build_graph(trace_dir=tmp_path).get_graph()
    agents = {"intake", "extraction", "rules", "computation", "review"}
    for edge in graph.edges:
        if edge.source in agents:
            assert edge.target == "orchestrator", "agents may only hand back to the orchestrator"
    to_agents = {e.target for e in graph.edges if e.source == "orchestrator"}
    assert agents <= to_agents


def test_multi_turn_intake_same_thread(tmp_path):
    graph = build_graph(trace_dir=tmp_path)
    config = cfg("t-turns")

    first = graph.invoke(clean_case(turns=1), config)
    assert first["status"] == "awaiting_user" and not first.get("done")
    assert first["pending_question"]

    # invoking again with no new message makes no progress
    again = graph.invoke({}, config)
    assert again["status"] == "awaiting_user"
    assert len(again["messages"]) == len(first["messages"])

    final = graph.invoke({"messages": [user("I am 70, single, with one W-2.")]}, config)
    assert final["status"] == "complete"
    assert final["pending_question"] is None
    assert final["handoff_log"][-1]["to"] == "end"


def test_orchestrator_view_is_bounded():
    from src.orchestration.context import MAX_HANDOFFS_IN_VIEW, MAX_REASON_CHARS, routing_view
    from src.orchestration.tokens import estimate_tokens
    from src.scenarios import document

    def state(n_docs, n_log):
        return {
            "documents": [document(f"doc-{i}") for i in range(n_docs)],
            "handoff_log": [
                {"step": i, "from": "orchestrator", "to": "intake", "reason": "x" * 500}
                for i in range(n_log)
            ],
            "messages": [user("hello")] * 200,
        }

    small, big = routing_view(state(1, 1)), routing_view(state(500, 400))
    assert len(big["last_handoffs"]) == MAX_HANDOFFS_IN_VIEW
    assert all(len(h["reason"]) <= MAX_REASON_CHARS for h in big["last_handoffs"])
    assert big["n_docs_pending"] == 500
    # size does not grow with documents, log length or chat length
    assert estimate_tokens(big) - estimate_tokens(small) < 80
