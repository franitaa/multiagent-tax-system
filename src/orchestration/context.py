"""Scoped views of state: each agent gets the smallest view it needs.

Phase 1 holds the projection only. Message trimming, the rolling session summary and the
per-document extraction view arrive in later phases. With scoped=False (the
--no-context-strategy flag) every agent gets the full state, for measurement.
"""
from typing import Any, Mapping

from src.orchestration.access import ALWAYS_READ, POLICY


MAX_HANDOFFS_IN_VIEW = 3
MAX_REASON_CHARS = 60


def routing_view(state: Mapping[str, Any]) -> dict[str, Any]:
    """Compact, bounded view for the orchestrator: flags and counts only. No documents,
    no chat, no id lists, so its size does not grow with the length of the session."""
    review = state.get("review") or {}
    extracted = state.get("extracted", {})
    escalation = state.get("escalation") or {}
    eligibility = state.get("eligibility") or {}
    pending_docs = [d for d in state.get("documents", []) if d["id"] not in extracted]
    return {
        "status": state.get("status", "running"),
        "done": state.get("done", False),
        "step": state.get("step", 0),
        # condition code only; the free-text reason stays out of the orchestrator's view
        "escalation": (
            {"pending": bool(escalation.get("pending")), "condition": escalation.get("condition")}
            if escalation
            else None
        ),
        # conditions a human already resolved with "continue" (at most 8 distinct values)
        "resolved_conditions": sorted(
            {d["condition"] for d in state.get("human_decisions", []) if d["decision"] == "continue"}
        ),
        "n_messages": len(state.get("messages", [])),
        "has_pending_question": bool(state.get("pending_question")),
        "awaiting_since_msgs": state.get("awaiting_since_msgs"),
        "intake_complete": state.get("intake_complete", False),
        "n_docs_pending": len(pending_docs),
        "has_eligibility": bool(eligibility),
        "in_scope": eligibility.get("in_scope"),
        "has_computed": bool(state.get("computed")),
        "review_verdict": review.get("verdict"),
        "last_handoffs": [
            {"step": e["step"], "to": e["to"], "reason": e["reason"][:MAX_REASON_CHARS]}
            for e in state.get("handoff_log", [])[-MAX_HANDOFFS_IN_VIEW:]
        ],
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
