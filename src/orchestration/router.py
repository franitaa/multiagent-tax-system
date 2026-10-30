"""Routing as a pure function of the orchestrator's routing view.

route(view) -> Route(next, reason, update). No I/O and no state mutation, so the decision
table is unit-testable. The orchestrator node applies `update` to state.

Rules, first match wins: pending escalation -> human; done -> end; waiting for the taxpayer
-> end (yield); intake -> extraction -> rules -> (out of scope -> human) -> (an income form the
taxpayer has but no amount is held for -> human, once: INCOME_NOT_READ) -> computation -> review; a passed review ends the case (never with an empty filing status or eligibility
verdict: that escalates as ELIGIBILITY_UNDECIDED, stop-only); a failed review is sent back to Computation until
`max_revisions` is used up, then escalates. The loop guard (guard.py) wraps this function.

Send-back clears the stale verdict (review=None) and counts the round, so the router can
never loop on an old "fail": with no review in state, the next hop is Review again.
"""
from dataclasses import dataclass, field
from typing import Any, Mapping

from src.state import (
    AWAITING_HUMAN, AWAITING_USER, COMPLETE, ELIGIBILITY_UNDECIDED, END_KEY, HUMAN_KEY,
    INCOME_NOT_READ, OUT_OF_SCOPE, RUNNING, REVIEW_BOUND_EXCEEDED,
)


# Work can only be sent back to Computation for now: sending it to Rules would also
# invalidate every computed line (open question for the Review owner, see docs/STATUS.md).
SEND_BACK_TARGET = "computation"


@dataclass(frozen=True)
class Route:
    next: str  # an agent name or END_KEY
    reason: str
    update: dict[str, Any] = field(default_factory=dict)


def _undecided(view: Mapping[str, Any], base: dict[str, Any]) -> Route:
    gaps = ", ".join(view["eligibility_gaps"])
    return Route(
        HUMAN_KEY,
        f"eligibility undecided: missing {gaps}",
        {
            **base,
            "status": AWAITING_HUMAN,
            "escalation": {
                "pending": True,
                "condition": ELIGIBILITY_UNDECIDED,
                "reason": f"Eligibility & Rules did not return: {gaps}. "
                          "A draft cannot be completed without them.",
                "raised_by": "orchestrator",
            },
        },
    )


def _income_not_read(forms: list[str], base: dict[str, Any]) -> Route:
    names = ", ".join(forms)
    return Route(
        HUMAN_KEY,
        f"income form not read: {names}",
        {
            **base,
            "status": AWAITING_HUMAN,
            "escalation": {
                "pending": True,
                "condition": INCOME_NOT_READ,
                "reason": f"The taxpayer has {names}, but no amount from it reached the return, so the draft "
                          "would leave that income out. Compare with the paper form. Continue only with a "
                          "note saying how it was handled; the draft still warns where it can.",
                "raised_by": "orchestrator",
            },
        },
    )


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
    if view["eligibility_gaps"]:
        return _undecided(view, base)
    gaps = view.get("income_gaps") or []
    if gaps and not view.get("income_gap_acknowledged"):
        return _income_not_read(gaps, base)
    if not view["has_computed"]:
        return Route("computation", "no computed lines", base)
    verdict = view["review_verdict"]
    if verdict is None:
        # also drops the revision request once its target has run
        update = {**base, **({"pending_revision": None} if view["has_pending_revision"] else {})}
        return Route("review", "return not yet reviewed", update)
    if verdict == "pass":
        if view["eligibility_gaps"]:  # never finish without a filing status and a verdict
            return _undecided(view, base)
        return Route(END_KEY, "review passed: draft ready", {**base, "done": True, "status": COMPLETE})
    if verdict != "fail":
        raise ValueError(f"invalid review verdict {verdict!r}: expected 'pass' or 'fail'")

    rounds = view["revision_count"]
    if rounds >= view["max_revisions"]:
        return Route(
            HUMAN_KEY,
            f"review still failing after {rounds} revision rounds",
            {
                **base,
                "status": AWAITING_HUMAN,
                "escalation": {
                    "pending": True,
                    "condition": REVIEW_BOUND_EXCEEDED,
                    "reason": f"Review still failing after {rounds} revision rounds",
                    "raised_by": "orchestrator",
                },
            },
        )
    fail = view["review_fail"] or {}
    requested = fail.get("send_back_to")
    findings = fail.get("findings", [])
    note = "" if requested in (None, SEND_BACK_TARGET) else f" (asked for {requested}; only {SEND_BACK_TARGET} supported)"
    return Route(
        SEND_BACK_TARGET,
        f"review failed: revision round {rounds + 1} of {view['max_revisions']}{note}",
        {
            **base,
            "status": RUNNING,
            "review": None,  # the verdict is now stale
            "revision_count": rounds + 1,
            "review_history": [{"round": rounds + 1, "requested": requested,
                                "sent_to": SEND_BACK_TARGET, "findings": findings}],
            "pending_revision": {"target": SEND_BACK_TARGET, "round": rounds + 1, "findings": findings},
        },
    )
