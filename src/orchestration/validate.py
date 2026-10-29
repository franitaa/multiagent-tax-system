"""Shape checks on what an agent returns, applied by the runner after the write allow-list.

The allow-list says which fields an agent may write. This says what those values may look like,
so text that talks an agent into misbehaving (prompt injection in a document, for example) cannot
smuggle in oversized or malformed output, a dollar amount without its provenance, or a handoff
the orchestrator cannot read. Checks are deliberately generic; each agent's own rules stay in
the agent. Returns problems as strings; an empty list means the update is acceptable.
"""
import json
from typing import Any

from src.state import AGENT_NAMES, END_KEY, ESCALATION_PRIORITY, HUMAN_KEY

MAX_STRING_CHARS = 5000
MAX_REASON_CHARS = 300
MAX_DEPTH = 10
MAX_UPDATE_BYTES = 250_000
RECORD_KEYS = ("value", "formula", "inputs", "source", "tool")
HANDOFF_TARGETS = frozenset(AGENT_NAMES) | {END_KEY, HUMAN_KEY, "orchestrator"}


def _walk(value: Any, path: str, depth: int, problems: list[str]) -> None:
    if depth > MAX_DEPTH:
        problems.append(f"{path}: nested deeper than {MAX_DEPTH} levels")
    elif isinstance(value, str):
        if len(value) > MAX_STRING_CHARS:
            problems.append(f"{path}: text longer than {MAX_STRING_CHARS} characters")
    elif isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                problems.append(f"{path}: non-text key {key!r}")
            else:
                _walk(item, f"{path}.{key}", depth + 1, problems)
    elif isinstance(value, (list, tuple)):
        for i, item in enumerate(value):
            _walk(item, f"{path}[{i}]", depth + 1, problems)
    elif not (value is None or isinstance(value, (bool, int, float))):
        problems.append(f"{path}: {type(value).__name__} is not plain data")


def _handoff(request: Any) -> list[str]:
    if not isinstance(request, dict):
        return ["handoff_request: must be a mapping"]
    problems = []
    if request.get("to") not in HANDOFF_TARGETS:
        problems.append(f"handoff_request.to: {request.get('to')!r} is not a known target")
    reason = request.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        problems.append("handoff_request.reason: required text")
    elif len(reason) > MAX_REASON_CHARS:
        problems.append(f"handoff_request.reason: longer than {MAX_REASON_CHARS} characters")
    return problems


def _escalation(flag: Any) -> list[str]:
    if flag is None:
        return []
    if not isinstance(flag, dict):
        return ["escalation: must be a mapping"]
    problems = []
    if flag.get("pending") and flag.get("condition") not in ESCALATION_PRIORITY:
        problems.append(f"escalation.condition: {flag.get('condition')!r} is not a known condition")
    if len(str(flag.get("reason", ""))) > MAX_REASON_CHARS:
        problems.append(f"escalation.reason: longer than {MAX_REASON_CHARS} characters")
    return problems


def _computed(lines: Any) -> list[str]:
    """Business rule 3: no dollar amount without a provenance record."""
    if not isinstance(lines, dict):
        return ["computed: must be a mapping of line -> provenance record"]
    problems = []
    for line, record in lines.items():
        if not isinstance(record, dict):
            problems.append(f"computed.{line}: not a provenance record")
            continue
        missing = [k for k in RECORD_KEYS if k not in record]
        if missing:
            problems.append(f"computed.{line}: provenance record lacks {missing}")
        value = record.get("value")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            problems.append(f"computed.{line}: value is not a number")
        if not isinstance(record.get("inputs", {}), dict):
            problems.append(f"computed.{line}: inputs is not a mapping")
    return problems


def _facts(facts: Any) -> list[str]:
    """Each answer is {"value", "source"} (docs/answer-names.md)."""
    if not isinstance(facts, dict):
        return ["facts: must be a mapping"]
    return [f"facts.{name}: needs both 'value' and 'source'" for name, fact in facts.items()
            if not (isinstance(fact, dict) and "value" in fact and "source" in fact)]


def check_update(agent: str, update: dict) -> list[str]:
    """Problems with `update` (empty when fine)."""
    problems: list[str] = []
    for field, value in update.items():
        _walk(value, field, 0, problems)
    try:
        size = len(json.dumps(update, default=str))
    except (TypeError, ValueError):
        size = 0
        problems.append("update: not serialisable")
    if size > MAX_UPDATE_BYTES:
        problems.append(f"update: larger than {MAX_UPDATE_BYTES} bytes")
    if "handoff_request" in update and update["handoff_request"] is not None:
        problems += _handoff(update["handoff_request"])
    if "escalation" in update:
        problems += _escalation(update["escalation"])
    if "computed" in update:
        problems += _computed(update["computed"])
    if "facts" in update:
        problems += _facts(update["facts"])
    return problems
