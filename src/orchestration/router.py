"""Routing as a pure function of the orchestrator's routing view.

route(view) -> Route(next, reason, update). No I/O and no state mutation, so the decision
table is unit-testable. The orchestrator node applies `update` to state.

Implemented: escalation, yield-to-user, the clean path, and the out-of-scope check. The
loop-guard and review-fail rows arrive in phase 3 and raise NotImplementedError until then
so nothing fails silently.
"""
from dataclasses import dataclass, field
from typing import Any, Mapping

from src.state import (
    AWAITING_HUMAN, AWAITING_USER, COMPLETE, END_KEY, HUMAN_KEY, OUT_OF_SCOPE, RUNNING,
)


@dataclass(frozen=True)
class Route:
    next: str  # an agent name or END_KEY
    reason: str
    update: dict[str, Any] = field(default_factory=dict)


def route(view: Mapping[str, Any]) -> Route:
    since = view.get("awaiting_since_msgs")
    answered = since is not None and view["n_messages"] > since
    base: dict[str, Any] = {}
    if answered:
        # The taxpayer replied since we yielded: clear the wait.
        base = {"awaiting_since_msgs": None, "pending_question": None, "status": RUNNING}

    escalation = view.get("escalation")
    if escalation and escalation.get("pending"):
        return Route(
            HUMAN_KEY,
            f"escalation raised: {escalation['condition']}",
            {**base, "status": AWAITING_HUMAN},
        )
    if view["done"]:
        return Route(END_KEY, "already complete", base)
    if since is not None and not answered:
        return Route(END_KEY, "still awaiting user reply", {})
    if view["has_pending_question"] and not answered:
        return Route(
            END_KEY,
            "yield: intake asked a question",
            {"status": AWAITING_USER, "awaiting_since_msgs": view["n_messages"]},
        )
    if not view["intake_complete"]:
        return Route("intake", "intake not complete", base)
    if view["n_docs_pending"] > 0:
        return Route("extraction", "documents not yet extracted", base)
    if not view["has_eligibility"]:
        return Route("rules", "eligibility not decided", base)
    if view["in_scope"] is False:
        return Route(
            HUMAN_KEY,
            "rules found the return out of scope",
            {
                **base,
                "status": AWAITING_HUMAN,
                "escalation": {
                    "pending": True,
                    "condition": OUT_OF_SCOPE,
                    "reason": "Eligibility & Rules marked the return out of scope",
                    "raised_by": "orchestrator",
                },
            },
        )
    if not view["has_computed"]:
        return Route("computation", "no computed lines", base)
    if view["review_verdict"] is None:
        return Route("review", "return not yet reviewed", base)
    if view["review_verdict"] == "pass":
        return Route(END_KEY, "review passed: draft ready", {**base, "done": True, "status": COMPLETE})
    raise NotImplementedError("review-fail routing arrives in phase 3")
