"""Bounded review -> revise cycle. Review reports, the orchestrator sends work back and
counts rounds, Computation revises, Review looks again. Review never fixes anything."""
import pytest
from langgraph.types import Command

from src import state as S
from src.agents import AGENTS
from src.graph import build_graph
from src.scenarios import clean_case
from tests.helpers import cfg, read_trace


class Scripted:
    """Review that passes only when `ok(view)`; Computation that improves each revision."""

    def __init__(self, ok):
        self.ok = ok
        self.review_views, self.computation_views = [], []

    def review(self, view, tools):
        self.review_views.append(view)
        ok = self.ok(view)
        return {
            "review": {
                "verdict": "pass" if ok else "fail",
                "findings": [] if ok else [{"line": "line_1a", "issue": "TEST finding"}],
                "send_back_to": None if ok else "computation",
            },
            "handoff_request": {"to": "end" if ok else "computation", "reason": "scripted"},
        }

    def computation(self, view, tools):
        self.computation_views.append(view)
        revisions = len(self.computation_views) - 1
        return {"computed": {"line_1a": {
            "value": 1000.0 * (revisions + 1), "formula": "TEST", "inputs": {},
            "source": "doc-1", "tool": "stub"}}}

    def agents(self):
        return {"review": self.review, "computation": self.computation}


def value_at_least(n):
    return lambda view: view["computed"]["line_1a"]["value"] >= n


def run(tmp_path, script, tid, **case):
    graph = build_graph(trace_dir=tmp_path, agents=script.agents())
    return graph, graph.invoke({**clean_case(), **case}, cfg(tid))


def test_fix_then_pass_ends_the_loop(tmp_path):
    script = Scripted(value_at_least(2000))  # first draft fails, the revision passes
    graph, result = run(tmp_path, script, "fix")

    assert result["status"] == S.COMPLETE and result["review"]["verdict"] == "pass"
    assert len(script.review_views) == 2 and len(script.computation_views) == 2
    assert result["revision_count"] == 1
    assert result["pending_revision"] is None
    assert [h["round"] for h in result["review_history"]] == [1]
    assert [e["to"] for e in result["handoff_log"]] == [
        "intake", "extraction", "rules", "computation", "review",
        "computation", "review", "end",
    ]
    # Computation was told what to fix, only on the revision call
    assert "pending_revision" not in script.computation_views[0]
    request = script.computation_views[1]["pending_revision"]
    assert request["target"] == "computation" and request["findings"][0]["issue"] == "TEST finding"


def test_router_never_sees_the_old_fail(tmp_path):
    script = Scripted(value_at_least(2000))
    graph, _ = run(tmp_path, script, "stale")
    history = list(graph.get_state_history(cfg("stale")))
    revising = [s for s in history if s.next == ("computation",) and s.values.get("revision_count") == 1]
    assert revising, "expected a checkpoint where the revision is about to run"
    assert all(s.values.get("review") is None for s in revising)


def test_default_bound_of_three_revisions_then_human(tmp_path):
    script = Scripted(lambda view: False)  # never good enough
    graph, result = run(tmp_path, script, "bound")

    assert len(script.review_views) == 4  # first look + 3 revisions
    assert len(script.computation_views) == 4
    payload = result["__interrupt__"][0].value
    assert payload["condition"] == S.REVIEW_BOUND_EXCEEDED and payload["raised_by"] == "orchestrator"
    assert payload["options"] == ["stop"]
    values = graph.get_state(cfg("bound")).values
    assert values["revision_count"] == 3 and len(values["review_history"]) == 3

    final = graph.invoke(Command(resume={"decision": "stop", "note": "back to the volunteer"}), cfg("bound"))
    assert final["status"] == S.HALTED_BY_HUMAN
    assert len(script.review_views) == 4, "no more reviews after the human stops the case"


def test_continue_is_not_allowed_when_the_bound_is_exceeded(tmp_path):
    script = Scripted(lambda view: False)
    graph, _ = run(tmp_path, script, "nocont")
    result = graph.invoke(Command(resume={"decision": "continue", "note": "ship it"}), cfg("nocont"))
    assert "can only be stopped" in result["__interrupt__"][0].value["error"]


@pytest.mark.parametrize("bound,reviews", [(0, 1), (1, 2), (2, 3), (5, 6)])
def test_custom_bound(tmp_path, bound, reviews):
    script = Scripted(lambda view: False)
    graph, result = run(tmp_path, script, f"b{bound}", max_revisions=bound)
    assert len(script.review_views) == reviews and len(script.computation_views) == reviews
    assert result["__interrupt__"][0].value["condition"] == S.REVIEW_BOUND_EXCEEDED
    assert graph.get_state(cfg(f"b{bound}")).values.get("revision_count", 0) == bound


def test_review_asking_for_rules_is_routed_to_computation_and_recorded(tmp_path):
    script = Scripted(value_at_least(2000))
    review = script.review

    def wants_rules(view, tools):
        update = review(view, tools)
        if update["review"]["verdict"] == "fail":
            update["review"]["send_back_to"] = "rules"
        return update

    graph = build_graph(trace_dir=tmp_path, agents={"review": wants_rules, "computation": script.computation})
    result = graph.invoke(clean_case(), cfg("rules"))
    assert result["status"] == S.COMPLETE
    assert result["review_history"][0]["requested"] == "rules"
    assert result["review_history"][0]["sent_to"] == "computation"
    assert any("only computation supported" in e["reason"] for e in result["handoff_log"])


def test_trace_shows_each_round(tmp_path):
    script = Scripted(value_at_least(3000))
    run(tmp_path, script, "trace")
    agents = [r["agent"] for r in read_trace(tmp_path, "trace") if r["agent"] in ("computation", "review")]
    assert agents == ["computation", "review"] * 3
