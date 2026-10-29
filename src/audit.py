"""Audit log: who did what to a case, and when. One append-only file per case.

What it records: events (an escalation raised, a volunteer's decision, a draft written or viewed,
a document flagged, a case purged), WHO caused them (`agent:<name>`, `volunteer:<name>`,
`taxpayer`, `system:<job>`) and when. What it never records: answers, amounts, document text or
identifiers. Free-text details (a volunteer's note) are redacted and truncated. Because it holds
no personal data it can outlive the case it describes (see src/retention.py).

Each entry carries the hash of the previous one, so editing or deleting a line in the middle is
detected by `verify`. Deleting the END of the file is not detected by the chain alone; keep the
file on storage the application user can only append to if that matters.

The dashboard should call `record(case_id, "viewed", actor="volunteer:<name>")` when a volunteer
opens a case, and `record(case_id, "volunteer_decision", ...)` is written for it by the runner when
the human gate returns a decision.
"""
import hashlib
import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

from security import redact_pii

MAX_TEXT_CHARS = 300
GENESIS = "0" * 64
_LOCK = threading.Lock()


def _safe_name(case_id) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", str(case_id))


def _clean(value):
    """Details are plain data only; text is redacted and shortened."""
    if isinstance(value, str):
        return redact_pii(value)[:MAX_TEXT_CHARS]
    if isinstance(value, bool) or value is None or isinstance(value, (int, float)):
        return value
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value][:50]
    return _clean(str(value))


def _digest(previous: str, body: dict) -> str:
    return hashlib.sha256((previous + json.dumps(body, sort_keys=True)).encode("utf-8")).hexdigest()


class AuditLog:
    def __init__(self, directory: str | Path):
        self.directory = Path(directory)

    def path(self, case_id) -> Path:
        return self.directory / f"{_safe_name(case_id)}.jsonl"

    def read(self, case_id) -> list[dict]:
        path = self.path(case_id)
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def record(self, case_id, event: str, actor: str, **details) -> dict:
        """Append one entry and return it."""
        if not event or not actor:
            raise ValueError("an audit entry needs an event and an actor")
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.path(case_id)
        with _LOCK:
            entries = self.read(case_id)
            body = {
                "seq": len(entries) + 1,
                "ts": datetime.now(timezone.utc).isoformat(),
                "case_id": _safe_name(case_id),
                "event": str(event)[:60],
                "actor": _clean(str(actor))[:80],
                "details": {str(k)[:40]: _clean(v) for k, v in details.items()},
            }
            previous = entries[-1]["hash"] if entries else GENESIS
            entry = {**body, "prev": previous, "hash": _digest(previous, body)}
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, sort_keys=True) + "\n")
        return entry

    def verify(self, case_id) -> list[str]:
        """Problems found in the chain (empty list = intact)."""
        problems, previous = [], GENESIS
        for i, entry in enumerate(self.read(case_id), start=1):
            body = {k: v for k, v in entry.items() if k not in ("prev", "hash")}
            if entry.get("seq") != i:
                problems.append(f"entry {i}: sequence is {entry.get('seq')}")
            if entry.get("prev") != previous:
                problems.append(f"entry {i}: does not follow the previous entry")
            if entry.get("hash") != _digest(entry.get("prev", ""), body):
                problems.append(f"entry {i}: content was changed")
            previous = entry.get("hash", "")
        return problems

    def last_activity(self, case_id) -> datetime | None:
        entries = self.read(case_id)
        return datetime.fromisoformat(entries[-1]["ts"]) if entries else None
