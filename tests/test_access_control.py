"""Centralised access: agents get only their view, write only their fields, call only
their tools, and cannot forge a handoff."""
import dataclasses
import json

import pytest

from src.graph import build_graph
from src.orchestration import access
from src.orchestration.access import AccessViolation, ToolBox
from src.scenarios import clean_case


def cfg(tid):
    return {"configurable": {"thread_id": tid}}


def test_agent_cannot_write_outside_its_allow_list(tmp_path):
    sneaky = lambda view, tools: {"computed": {"line_1a": {"value": 1}}}  # extraction may not
    graph = build_graph(trace_dir=tmp_path, agents={"extraction": sneaky})
    with pytest.raises(AccessViolation, match="computed"):
        graph.invoke(clean_case(), cfg("w"))
    records = [json.loads(x) for x in (tmp_path / "w.jsonl").read_text().splitlines()]
    assert records[-1]["agent"] == "extraction" and records[-1]["violations"] == ["computed"]


def test_violation_is_enforced_even_without_the_context_strategy(tmp_path):
    sneaky = lambda view, tools: {"facts": {"x": 1}}
    graph = build_graph(trace_dir=tmp_path, context_strategy=False, agents={"review": sneaky})
    with pytest.raises(AccessViolation):
        graph.invoke(clean_case(), cfg("w2"))


def test_agent_only_receives_its_scoped_view(tmp_path):
    seen = {}

    def spy(view, tools):
        seen.update(view)
        return {"extracted": {"doc-1": {"doc_id": "doc-1"}}}

    build_graph(trace_dir=tmp_path, agents={"extraction": spy}).invoke(clean_case(), cfg("v"))
    assert set(seen) <= {"documents", "escalation", "human_decisions"}
    assert "messages" not in seen and "facts" not in seen


def test_full_view_when_strategy_is_off(tmp_path):
    seen = {}

    def spy(view, tools):
        seen.update(view)
        return {"extracted": {"doc-1": {"doc_id": "doc-1"}}}

    build_graph(trace_dir=tmp_path, context_strategy=False, agents={"extraction": spy}).invoke(
        clean_case(), cfg("v2"))
    assert "messages" in seen and "facts" in seen


def test_tools_only_through_allow_list(monkeypatch):
    monkeypatch.setitem(access.TOOLS, "add", lambda a, b: a + b)
    monkeypatch.setitem(
        access.POLICY, "computation",
        dataclasses.replace(access.POLICY["computation"], tools=frozenset({"add"})),
    )
    box = ToolBox("computation")
    assert box.call("add", a=1, b=2) == 3 and box.calls == ["add"]
    with pytest.raises(AccessViolation):
        ToolBox("rules").call("add", a=1, b=2)  # rules has no tools


def test_called_tools_are_traced(tmp_path, monkeypatch):
    monkeypatch.setitem(access.TOOLS, "add", lambda a, b: a + b)
    monkeypatch.setitem(
        access.POLICY, "computation",
        dataclasses.replace(access.POLICY["computation"], tools=frozenset({"add"})),
    )

    def computes(view, tools):
        tools.call("add", a=1, b=2)
        return {"computed": {"line_1a": {"value": 3}}}

    build_graph(trace_dir=tmp_path, agents={"computation": computes}).invoke(clean_case(), cfg("t"))
    records = [json.loads(x) for x in (tmp_path / "t.jsonl").read_text().splitlines()]
    assert next(r for r in records if r["agent"] == "computation")["tools_called"] == ["add"]


def test_handoff_sender_cannot_be_forged(tmp_path):
    forger = lambda view, tools: {
        "extracted": {"doc-1": {"doc_id": "doc-1"}}, "handoff_request": {"from": "review", "to": "rules", "reason": "x"}}
    graph = build_graph(trace_dir=tmp_path, agents={"extraction": forger})
    result = graph.invoke(clean_case(), cfg("f"))
    entry = next(e for e in result["handoff_log"] if e["requested_by"] is not None
                 and e["requested_to"] == "rules")
    assert entry["requested_by"] == "extraction"
