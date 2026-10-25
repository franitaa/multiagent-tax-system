"""The human gate: the orchestrator-owned node that performs the LangGraph interrupt.

Agents only set an `escalation` flag; the router sends control here. The interrupt is the
FIRST statement because LangGraph re-executes the node from the top on resume, so nothing
before it may have side effects.

Resume value: {"decision": "continue" | "stop", "note": str}.
  continue: a human has reviewed and takes responsibility; the flag is cleared and the
            condition is recorded as resolved so it is not raised again.
  stop:     the case ends with status "halted_by_human".
"""
from langgraph.types import interrupt

from src.orchestration.access import ToolBox
from src.state import HALTED_BY_HUMAN, RUNNING

DECISIONS = ("continue", "stop")


def human_gate(view: dict, tools: ToolBox) -> dict:
    escalation = view["escalation"]
    answer = interrupt(
        {
            "case_id": view.get("case_id"),
            "condition": escalation["condition"],
            "reason": escalation.get("reason", ""),
            "raised_by": escalation.get("raised_by"),
            "options": list(DECISIONS),
        }
    )
    if not isinstance(answer, dict) or answer.get("decision") not in DECISIONS:
        raise ValueError(f"resume value must be {{'decision': one of {DECISIONS}, 'note': str}}")

    update = {
        "human_decisions": [
            {
                "condition": escalation["condition"],
                "decision": answer["decision"],
                "note": answer.get("note", ""),
            }
        ],
        "escalation": None,
        "status": RUNNING,
    }
    if answer["decision"] == "stop":
        update.update(status=HALTED_BY_HUMAN, done=True)
    return update
