"""Loop guard: break out of a pathological handoff cycle by escalating to a human.

A pure wrapper around the router: apply_guard(view, route(view)) -> Route. Two rules, both
checked only when the orchestrator is about to dispatch an agent:

  1. State repeated: the routing-relevant fingerprint was already seen in this run segment,
     i.e. the last agent changed nothing that affects routing (empty or no-op output).
  2. Hop repeated: the same agent would be dispatched more than MAX_CONSECUTIVE times in a
     row, even though the state keeps changing a little (e.g. an agent that appends a message
     every time but never finishes).

Legitimate cycles are not flagged: the review loop changes revision_count and the review
verdict on every round, so its fingerprints differ. The history is cleared whenever the
orchestrator yields to the taxpayer, ends, or hands to a human, so a new call starts fresh.
It keeps the last MAX_SEEN fingerprints (8 hex chars each), so the view stays bounded; a cycle
longer than that would be caught by rule 2 only if it keeps hitting the same agent.
"""
import hashlib
import json
from typing import Any, Mapping

from src.orchestration.router import Route
from src.state import AWAITING_HUMAN, END_KEY, HUMAN_KEY, LOOP_GUARD

MAX_SEEN = 24
MAX_CONSECUTIVE = 3

FINGERPRINT_KEYS = (
    "done", "n_messages", "has_pending_question", "awaiting_since_msgs", "intake_complete",
    "n_docs_pending", "has_eligibility", "in_scope", "has_computed", "review_verdict",
    "revision_count", "has_pending_revision", "escalation", "n_human_decisions",
)


def fingerprint(view: Mapping[str, Any]) -> str:
    """Hash of what routing depends on. Excludes step counters, logs and status text."""
    relevant = {k: view.get(k) for k in FINGERPRINT_KEYS}
    return hashlib.sha256(json.dumps(relevant, sort_keys=True, default=str).encode()).hexdigest()[:8]


def _trip(why: str) -> Route:
    return Route(
        HUMAN_KEY,
        f"loop guard: {why}",
        {
            "status": AWAITING_HUMAN,
            "guard": {},
            "escalation": {
                "pending": True,
                "condition": LOOP_GUARD,
                "reason": f"Handoff loop detected: {why}",
                "raised_by": "orchestrator",
            },
        },
    )


def apply_guard(view: Mapping[str, Any], decision: Route) -> Route:
    if decision.next in (END_KEY, HUMAN_KEY):
        return Route(decision.next, decision.reason, {**decision.update, "guard": {}})

    guard = view.get("guard") or {}
    seen = guard.get("seen", [])
    fp = fingerprint(view)
    if fp in seen:
        return _trip(f"no progress: state unchanged since the last visit (before {decision.next})")
    streak = guard.get("streak", 0) + 1 if guard.get("last") == decision.next else 1
    if streak > MAX_CONSECUTIVE:
        return _trip(f"{decision.next} would be dispatched {streak} times in a row")

    new_guard = {"seen": [*seen, fp][-MAX_SEEN:], "last": decision.next, "streak": streak}
    return Route(decision.next, decision.reason, {**decision.update, "guard": new_guard})
