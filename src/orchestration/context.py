"""Context strategy: each agent gets the smallest view of state that lets it do its job.

Selective recall by construction (see docs/decisions/001-context-strategy.md):
  * a view is a projection of the fields in the agent's read allow-list (access.POLICY),
    some narrowed further (TRANSFORMS below);
  * the one place a window is still needed is Intake's chat: the last MAX_INTAKE_MESSAGES
    messages, with everything older recalled through `facts` (structured, lossless);
  * a deterministic rolling `session_summary` (decisions and flags only, never amounts or
    chat text) gives agents the history of the session without the raw material;
  * escalation and human decisions are in every view, so a safety signal is never scoped away.

With scoped=False (the --no-context-strategy flag) every agent gets the full state, so the
same scenario can be measured both ways.
"""
from typing import Any, Mapping

from src.orchestration.access import ALWAYS_READ, POLICY
from src.state import DEFAULT_MAX_REVISIONS


MAX_HANDOFFS_IN_VIEW = 3
MAX_REASON_CHARS = 60
MAX_INTAKE_MESSAGES = 6
MAX_HUMAN_DECISIONS_IN_SUMMARY = 5


def _numeric_facts(facts: Mapping[str, Any]) -> dict[str, Any]:
    """Computation works from numbers, not free text."""
    return {
        name: fact for name, fact in facts.items()
        if isinstance(fact.get("value"), (int, float)) and not isinstance(fact.get("value"), bool)
    }


# Per-agent narrowing of the fields on the read allow-list.
TRANSFORMS = {
    "intake": {"messages": lambda messages: messages[-MAX_INTAKE_MESSAGES:]},
    "computation": {
        "facts": _numeric_facts,
        "eligibility": lambda e: {"filing_status": e.get("filing_status")},
    },
}


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
        "n_messages": len(state.get("messages", [])),
        "n_documents": len(state.get("documents", [])),
        "has_pending_question": bool(state.get("pending_question")),
        "awaiting_since_msgs": state.get("awaiting_since_msgs"),
        "intake_complete": state.get("intake_complete", False),
        "n_docs_pending": len(pending_docs),
        "has_eligibility": bool(eligibility),
        "in_scope": eligibility.get("in_scope"),
        "has_computed": bool(state.get("computed")),
        "review_verdict": review.get("verdict"),
        "revision_count": state.get("revision_count", 0),
        "max_revisions": state.get("max_revisions", DEFAULT_MAX_REVISIONS),
        "has_pending_revision": bool(state.get("pending_revision")),
        "n_human_decisions": len(state.get("human_decisions", [])),
        "last_handoffs": [
            {"step": e["step"], "to": e["to"], "reason": e["reason"][:MAX_REASON_CHARS]}
            for e in state.get("handoff_log", [])[-MAX_HANDOFFS_IN_VIEW:]
        ],
        "handoff_request": state.get("handoff_request"),
    }


def control_view(state: Mapping[str, Any]) -> dict[str, Any]:
    """Inputs the orchestrator's DETERMINISTIC code needs but a model would never be shown:
    the loop guard's fingerprint history and a failed review's findings (which the router
    copies, uninterpreted, into the revision request). Kept out of the routing view so the
    view stays what an LLM orchestrator could safely be given, and out of the token counts."""
    review = state.get("review") or {}
    decisions = state.get("human_decisions", [])[-MAX_HUMAN_DECISIONS_IN_SUMMARY:]
    return {
        "human_summary": [f"{d['condition']}={d['decision']}" for d in decisions],
        "guard": state.get("guard") or {},
        "review_fail": (
            {"send_back_to": review.get("send_back_to"), "findings": review.get("findings", [])}
            if review.get("verdict") == "fail"
            else None
        ),
    }


def decision_inputs(state: Mapping[str, Any]) -> dict[str, Any]:
    """Everything route() and apply_guard() read: the routing view plus the control inputs."""
    return {**routing_view(state), **control_view(state)}


class View(dict):
    """A view handed to an agent. `.control` holds extra inputs for deterministic code; it is
    an attribute, not a key, so it is never counted as part of what an agent is shown."""

    control: dict = {}


def view_for(agent: str, state: Mapping[str, Any], scoped: bool = True) -> View:
    if agent == "orchestrator":
        view = View(routing_view(state) if scoped else {**state, **routing_view(state)})
        view.control = control_view(state)
        return view
    if not scoped:
        return View(state)
    keys = POLICY[agent].reads | set(ALWAYS_READ)
    narrow = TRANSFORMS.get(agent, {})
    return View({k: narrow.get(k, lambda v: v)(state[k]) for k in keys if k in state})


def summarise(inputs: Mapping[str, Any]) -> str:
    """Rolling summary of session decisions, rebuilt by the orchestrator at every visit.

    Deterministic and bounded. It holds milestones, counts and condition codes only: no
    dollar amounts (those live in `computed` with provenance), no chat text, no names.
    `inputs` is the orchestrator's decision inputs (routing view + control)."""
    parts = [
        f"intake {'complete' if inputs['intake_complete'] else 'in progress'} "
        f"({inputs['n_messages']} messages)"
    ]
    if inputs["n_documents"]:
        done = inputs["n_documents"] - inputs["n_docs_pending"]
        parts.append(f"documents extracted {done}/{inputs['n_documents']}")
    if inputs["has_eligibility"]:
        parts.append("eligibility: in scope" if inputs["in_scope"] is not False else "eligibility: out of scope")
    if inputs["has_computed"]:
        parts.append("lines computed")
    if inputs["revision_count"]:
        parts.append(f"review revision rounds: {inputs['revision_count']}")
    if inputs["review_verdict"]:
        parts.append(f"review: {inputs['review_verdict']}")
    parts.extend(f"human: {item}" for item in inputs.get("human_summary", []))
    return "; ".join(parts)
