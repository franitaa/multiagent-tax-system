"""The orchestrator node: the only place that decides the next hop and when to stop.

It receives the compact routing view (never documents or chat), asks the pure router for a
decision, validates the previous agent's handoff request against ALLOWED_HANDOFFS, and
returns a state update plus a handoff_log entry. It does not extract, compute, or talk to
the user.
"""
from src.orchestration.access import ToolBox
from src.orchestration.router import route
from src.state import ALLOWED_HANDOFFS


def _check_request(request: dict | None, routed_to: str) -> dict:
    if not request:
        return {"requested_by": None, "requested_to": None, "honored": None}
    sender, wanted = request.get("from"), request.get("to")
    valid = wanted in ALLOWED_HANDOFFS.get(sender, frozenset())
    return {
        "requested_by": sender,
        "requested_to": wanted,
        "honored": valid and wanted == routed_to,
    }


def orchestrate(view: dict, tools: ToolBox) -> dict:
    decision = route(view)
    step = view.get("step", 0) + 1
    entry = {
        "step": step,
        "from": "orchestrator",
        "to": decision.next,
        "reason": decision.reason,
        **_check_request(view.get("handoff_request"), decision.next),
    }
    return {
        "next_agent": decision.next,
        "step": step,
        "handoff_log": [entry],
        "handoff_request": None,
        **decision.update,
    }
