"""Shared state contract for the SilverFile graph.

Owned by Person 1 (orchestration) and agreed with the inter-agent communication
owner. Agents never see this whole object (see src/orchestration/context.py);
they return a partial update limited to the fields their policy allows
(src/orchestration/access.py).

Values stored in state are plain JSON-like data so any checkpointer can persist them.
"""
import json
from typing import Annotated, Any, TypedDict

from provenance import ProvenanceRecord

DEFAULT_MAX_REVISIONS = 3

# Routing targets. "end" ends the current graph call (either done or yielding to the UI).
AGENT_NAMES = ("intake", "extraction", "rules", "computation", "review")
END_KEY = "end"
HUMAN_KEY = "human"

# status values
RUNNING = "running"
AWAITING_USER = "awaiting_user"  # call returned normally; UI shows pending_question
AWAITING_HUMAN = "awaiting_human"  # call returned with an interrupt (volunteer)
COMPLETE = "complete"
HALTED_BY_HUMAN = "halted_by_human"

# Escalation conditions (a human decides via interrupt).
OUT_OF_SCOPE = "OUT_OF_SCOPE"
SOURCE_CONFLICT = "SOURCE_CONFLICT"
FORM_1099R_BOX_2B = "FORM_1099R_BOX_2B"
TAX_ADVICE_REQUEST = "TAX_ADVICE_REQUEST"
FILING_STATUS_AMBIGUITY = "FILING_STATUS_AMBIGUITY"
EXPLOITATION_SIGNS = "EXPLOITATION_SIGNS"
# raised by the orchestrator itself
LOOP_GUARD = "LOOP_GUARD"
REVIEW_BOUND_EXCEEDED = "REVIEW_BOUND_EXCEEDED"
# Most severe first. Decides which of several simultaneous escalations a human sees first.
ESCALATION_PRIORITY = (
    EXPLOITATION_SIGNS,
    OUT_OF_SCOPE,
    FORM_1099R_BOX_2B,
    FILING_STATUS_AMBIGUITY,
    SOURCE_CONFLICT,
    TAX_ADVICE_REQUEST,
    LOOP_GUARD,
    REVIEW_BOUND_EXCEEDED,
)
AGENT_CONDITIONS = (
    OUT_OF_SCOPE,
    SOURCE_CONFLICT,
    FORM_1099R_BOX_2B,
    TAX_ADVICE_REQUEST,
    FILING_STATUS_AMBIGUITY,
    EXPLOITATION_SIGNS,
)

# Which hops an agent may *request*. The orchestrator treats a request as advisory:
# it validates it here, then routes by state and logs whether it honoured the request.
ALLOWED_HANDOFFS: dict[str, frozenset[str]] = {
    "intake": frozenset({"extraction", "rules", END_KEY, HUMAN_KEY}),
    "extraction": frozenset({"rules", "intake", HUMAN_KEY}),
    "rules": frozenset({"computation", "intake", HUMAN_KEY}),
    "computation": frozenset({"review", HUMAN_KEY}),
    "review": frozenset({"computation", "rules", END_KEY, HUMAN_KEY}),
}


class Message(TypedDict):
    role: str  # "user" | "assistant"
    content: str


class DocRef(TypedDict):
    id: str
    kind: str  # e.g. "W-2", "1099-R"
    text: str


class Handoff(TypedDict):
    """Handoff request an agent returns. `from` is stamped by the runner, not trusted."""

    to: str
    reason: str


class Escalation(TypedDict, total=False):
    pending: bool
    condition: str  # one of the conditions above
    reason: str
    raised_by: str
    queued: list  # other escalations raised at the same moment; shown to the human in turn


# ---- reducers -------------------------------------------------------------------


def append_list(old: list | None, new: list | None) -> list:
    return [*(old or []), *(new or [])]


def merge_dict(old: dict | None, new: dict | None) -> dict:
    return {**(old or {}), **(new or {})}


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def merge_extracted(old: dict | None, new: dict | None) -> dict:
    """Merge extraction results keyed by doc_id, independent of arrival order.

    Commutative and associative: keys are unioned and, if the same doc_id arrives twice
    with different records, the one with the larger canonical JSON wins. Parallel
    extraction workers can therefore finish in any order.
    """
    old, new = old or {}, new or {}
    merged: dict = {}
    for key in sorted(old.keys() | new.keys()):
        candidates = [side[key] for side in (old, new) if key in side]
        merged[key] = max(candidates, key=_canonical)
    return merged


def merge_request(old: dict | None, new: dict | None) -> dict | None:
    """handoff_request. The orchestrator clears it with None after each hop. If parallel
    workers each return one, keep the canonical-max so the result ignores arrival order."""
    if new is None or old is None:
        return new
    return max((old, new), key=_canonical)


def _severity(esc: dict) -> tuple:
    condition = esc.get("condition")
    rank = ESCALATION_PRIORITY.index(condition) if condition in ESCALATION_PRIORITY else len(ESCALATION_PRIORITY)
    return rank, _canonical({k: v for k, v in esc.items() if k != "queued"})


def merge_escalation(old: dict | None, new: dict | None) -> dict | None:
    """escalation. Parallel workers may each raise a flag; none may be lost and the result
    must not depend on arrival order. The most severe becomes the active flag and the rest
    go in its `queued` list, sorted. None clears. {..., "replace": True} overwrites (used by
    the human gate to promote the next queued flag)."""
    if new is None:
        return None
    if new.get("replace"):
        return {k: v for k, v in new.items() if k != "replace"}
    if not old or not old.get("pending"):
        return new
    if not new.get("pending"):
        return old
    flags = [{k: v for k, v in e.items() if k != "queued"}
             for e in (old, *old.get("queued", []), new, *new.get("queued", []))]
    unique = {_canonical(f): f for f in flags}.values()
    first, *rest = sorted(unique, key=_severity)
    return {**first, "queued": rest} if rest else first


class SilverState(TypedDict, total=False):
    # --- input / identity
    case_id: str
    documents: list[DocRef]
    # --- Intake (the only agent that talks to the taxpayer)
    messages: Annotated[list[Message], append_list]
    facts: Annotated[dict[str, Any], merge_dict]  # name -> {"value": ..., "source": ...}
    pending_question: str | None  # Intake sets; orchestrator clears once the user replies
    intake_complete: bool
    # --- Document Extraction
    extracted: Annotated[dict[str, Any], merge_extracted]  # doc_id -> typed record
    # --- Eligibility & Rules
    eligibility: dict[str, Any]  # {in_scope, filing_status, citations[]}
    # --- Computation (every number carries a ProvenanceRecord)
    computed: Annotated[dict[str, ProvenanceRecord], merge_dict]
    # --- Review/Audit
    review: dict[str, Any] | None  # {verdict: pass|fail, findings[], send_back_to}
    review_history: Annotated[list[dict[str, Any]], append_list]  # phase 3
    pending_revision: dict[str, Any] | None  # phase 3: {target, findings}
    revision_count: int
    max_revisions: int
    # --- Handoffs / escalation (any agent may set `escalation`; only the orchestrator clears)
    handoff_request: Annotated[Handoff | None, merge_request]
    handoff_log: Annotated[list[dict[str, Any]], append_list]
    escalation: Annotated[Escalation | None, merge_escalation]
    human_decisions: Annotated[list[dict[str, Any]], append_list]  # phase 2
    # --- Orchestrator-owned control fields
    status: str
    done: bool
    step: int
    next_agent: str
    awaiting_since_msgs: int | None
    guard: dict[str, Any]  # phase 3
    session_summary: str  # phase 4
