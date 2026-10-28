"""The human gate: the orchestrator-owned node that performs the LangGraph interrupt.

Agents only set an `escalation` flag; the router sends control here. The interrupt is the
FIRST statement because LangGraph re-executes the node from the top on resume, so nothing
before it may have side effects.

Resume value: {"decision": "continue" | "stop", "note": str, "resolution": {...} | absent,
"reviewer": str | absent}. `reviewer` names the volunteer for the audit log (src/audit.py).

  stop      always allowed. The case ends with status "halted_by_human". Note optional.
  continue  allowed only for SOURCE_CONFLICT, FILING_STATUS_AMBIGUITY, TAX_ADVICE_REQUEST,
            and only with a non-empty note (it is part of the audit record). A human cannot
            take responsibility for out-of-scope work, so OUT_OF_SCOPE, FORM_1099R_BOX_2B,
            EXPLOITATION_SIGNS (and the orchestrator's own LOOP_GUARD,
            REVIEW_BOUND_EXCEEDED and ELIGIBILITY_UNDECIDED) accept "stop" only.
  resolution  optional resolving values, stored as facts with source "human:<CONDITION>":
            SOURCE_CONFLICT: {fact_name: value}; FILING_STATUS_AMBIGUITY: {"filing_status": ...}.

An invalid answer does not raise: the gate interrupts again with the same payload plus an
"error" message, so the UI shows the message and the volunteer answers again. (Raising would
leave the bad answer cached by LangGraph, and a corrected answer would replay it.) The resume
value must be a dict; Command(resume=None) is not supported by LangGraph.
"""
from langgraph.types import interrupt

from src.orchestration.access import ToolBox
from src.state import (
    AWAITING_HUMAN, FILING_STATUS_AMBIGUITY, HALTED_BY_HUMAN, RUNNING, SOURCE_CONFLICT, TAX_ADVICE_REQUEST,
)

CONTINUABLE = frozenset({SOURCE_CONFLICT, FILING_STATUS_AMBIGUITY, TAX_ADVICE_REQUEST})
FILING_STATUSES = (
    "single",
    "married_filing_jointly",
    "married_filing_separately",
    "head_of_household",
    "qualifying_surviving_spouse",
)
_SCALARS = (str, int, float, bool)


def allowed_decisions(condition: str) -> tuple[str, ...]:
    return ("continue", "stop") if condition in CONTINUABLE else ("stop",)


def _validate(answer, condition: str) -> tuple[str, str, dict]:
    if not isinstance(answer, dict) or not isinstance(answer.get("decision"), str):
        raise ValueError("resume value must be a dict like {'decision': 'stop', 'note': '...'}")
    decision, note = answer["decision"], str(answer.get("note") or "").strip()
    resolution = answer.get("resolution") or {}
    if decision not in ("continue", "stop"):
        raise ValueError(f"decision must be 'continue' or 'stop', got {decision!r}")
    if decision == "stop":
        if resolution:
            raise ValueError("a resolution only applies to 'continue'")
        return decision, note, {}
    if condition not in CONTINUABLE:
        raise ValueError(f"{condition} can only be stopped: a human cannot take responsibility for it")
    if not note:
        raise ValueError("'continue' requires a non-empty note (it goes in the audit record)")
    if resolution:
        if condition == TAX_ADVICE_REQUEST:
            raise ValueError("TAX_ADVICE_REQUEST has nothing to resolve; record the question in the note")
        if not isinstance(resolution, dict) or not all(
            isinstance(k, str) and k and isinstance(v, _SCALARS) for k, v in resolution.items()
        ):
            raise ValueError("resolution must map non-empty fact names to string/number/bool values")
        if condition == FILING_STATUS_AMBIGUITY:
            if set(resolution) != {"filing_status"} or resolution["filing_status"] not in FILING_STATUSES:
                raise ValueError(f"resolution must be {{'filing_status': one of {FILING_STATUSES}}}")
    return decision, note, dict(resolution)


def _reviewer(answer) -> str:
    name = answer.get("reviewer") if isinstance(answer, dict) else None
    return " ".join(str(name).split())[:80] if name else ""


def human_gate(view: dict, tools: ToolBox) -> dict:
    escalation = view["escalation"]
    condition = escalation["condition"]
    payload = {
        "case_id": view.get("case_id"),
        "condition": condition,
        "reason": escalation.get("reason", ""),
        "also_pending": [q["condition"] for q in escalation.get("queued") or []],
        "raised_by": escalation.get("raised_by"),
        "options": list(allowed_decisions(condition)),
        "note_required_for_continue": True,
        "resolution_fields": (
            ["filing_status"] if condition == FILING_STATUS_AMBIGUITY
            else ["<fact name>"] if condition == SOURCE_CONFLICT else []
        ),
    }
    while True:
        answer = interrupt(payload)  # re-asked with an "error" until the answer is valid
        try:
            decision, note, resolution = _validate(answer, condition)
            break
        except ValueError as exc:
            payload = {**payload, "error": str(exc)}

    update = {
        "human_decisions": [
            {"condition": condition, "decision": decision, "note": note,
             "resolution": resolution or None, **({"reviewer": _reviewer(answer)} if _reviewer(answer) else {})}
        ],
        "escalation": None,
        "status": RUNNING,
    }
    queued = escalation.get("queued") or []
    if queued:
        update["human_decisions"][0]["also_raised"] = [q["condition"] for q in queued]
    if resolution:
        update["facts"] = {
            name: {"value": value, "source": f"human:{condition}"}
            for name, value in resolution.items()
        }
    if decision == "stop":
        update.update(status=HALTED_BY_HUMAN, done=True)
    elif queued:
        # promote the next flag raised at the same moment; the human sees it next
        first, *rest = queued
        update["escalation"] = {**first, **({"queued": rest} if rest else {}), "replace": True}
        update["status"] = AWAITING_HUMAN
    return update
