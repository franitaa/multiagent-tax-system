"""Scoped views of state: each agent gets the smallest view it needs.

Phase 1 holds the projection only. Message trimming, the rolling session summary and the
per-document extraction view arrive in later phases. With scoped=False (the
--no-context-strategy flag) every agent gets the full state, for measurement.
"""
from typing import Any, Mapping

from src.orchestration.access import ALWAYS_READ, POLICY


def routing_view(state: Mapping[str, Any]) -> dict[str, Any]:
    """Compact view for the orchestrator: flags, counts, ids. No documents, no chat."""
    review = state.get("review") or {}
    return {
        "status": state.get("status", "running"),
        "done": state.get("done", False),
        "step": state.get("step", 0),
        "escalation": state.get("escalation"),
        "n_messages": len(state.get("messages", [])),
        "has_pending_question": bool(state.get("pending_question")),
        "awaiting_since_msgs": state.get("awaiting_since_msgs"),
        "intake_complete": state.get("intake_complete", False),
        "doc_ids": sorted(d["id"] for d in state.get("documents", [])),
        "extracted_ids": sorted(state.get("extracted", {})),
        "has_eligibility": bool(state.get("eligibility")),
        "has_computed": bool(state.get("computed")),
        "review_verdict": review.get("verdict"),
        "last_handoffs": state.get("handoff_log", [])[-3:],
        "handoff_request": state.get("handoff_request"),
    }


def view_for(agent: str, state: Mapping[str, Any], scoped: bool = True) -> dict[str, Any]:
    if agent == "orchestrator":
        view = routing_view(state)
        return view if scoped else {**state, **view}
    if not scoped:
        return dict(state)
    keys = POLICY[agent].reads | set(ALWAYS_READ)
    return {k: state[k] for k in keys if k in state}
