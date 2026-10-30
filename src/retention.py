"""Retention: delete a case's personal data on request, and expire cases nobody has touched.

A case lives in several places, all keyed by the case ID (= the LangGraph thread ID):
  runtime/team_checkpoints.sqlite   graph state: answers, dependents' test SSNs, extracted amounts
  runtime/intake_memory.sqlite      Intake's saved answers and their history
  runtime/documents/doc_<sha>.png   the document images the case used (content-addressed)
  runtime/uploads/<sha>.png         the upload a P3 document was read from (content-addressed)
  <trace dir>/<case>.jsonl          traces (field names only, no values)
  output/<case>_*.html              draft forms
`purge_case` removes all of them. A document image is kept if another case still uses it.
The audit log (src/audit.py) holds no personal data, so it is kept and gets a `case_purged`
entry saying who deleted the case, when, why and how many items went; the counts are the only
trace left.

Retention policy: a case idle for DEFAULT_RETENTION_DAYS is expired; an upload that never became
part of a case is deleted after STALE_UPLOAD_HOURS. Nothing runs these on a timer: schedule
`python -m scripts.purge_cases --expired` (cron, Task Scheduler, a container job).
"""
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.audit import AuditLog

DEFAULT_RETENTION_DAYS = 30
STALE_UPLOAD_HOURS = 24
CASE_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")


def _case_id(case_id) -> str:
    if not isinstance(case_id, str) or not CASE_ID.fullmatch(case_id):
        raise ValueError("a case ID is 1-64 letters, digits, underscores or hyphens")
    return case_id


def _safe(case_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", case_id)


UPLOAD_HANDLE = re.compile(r"[0-9a-f]{64}")


def _state_refs(value, key: str) -> set[str]:
    """Every string stored under `key` anywhere inside a saved state."""
    found = set()
    if isinstance(value, dict):
        for name, item in value.items():
            if name == key and isinstance(item, str):
                found.add(item)
            else:
                found |= _state_refs(item, key)
    elif isinstance(value, (list, tuple)):
        for item in value:
            found |= _state_refs(item, key)
    return found


class Layout:
    """Where a deployment keeps case data. Defaults match start.py / app.py / the CLI scenarios."""

    def __init__(self, runtime="runtime", trace_dirs=None, output_dir="output", audit_dir=None):
        self.runtime = Path(runtime)
        self.trace_dirs = [Path(d) for d in (trace_dirs or (self.runtime / "traces", "traces"))]
        self.output_dir = Path(output_dir)
        self.audit = AuditLog(audit_dir or self.trace_dirs[0] / "audit")

    @property
    def checkpoints(self) -> Path:
        return self.runtime / "team_checkpoints.sqlite"

    @property
    def intake_memory(self) -> Path:
        return self.runtime / "intake_memory.sqlite"

    @property
    def documents(self) -> Path:
        return self.runtime / "documents"

    @property
    def uploads(self) -> Path:
        return self.runtime / "uploads"


def _saver(layout: Layout):
    from langgraph.checkpoint.sqlite import SqliteSaver

    return SqliteSaver.from_conn_string(str(layout.checkpoints))


def _thread_ids(layout: Layout) -> set[str]:
    if not layout.checkpoints.exists():
        return set()
    connection = sqlite3.connect(layout.checkpoints)
    try:
        return {row[0] for row in connection.execute("SELECT DISTINCT thread_id FROM checkpoints")}
    except sqlite3.OperationalError:  # no checkpoints table yet
        return set()
    finally:
        connection.close()


def _stored_refs(layout: Layout, key: str) -> dict[str, set[str]]:
    """case ID -> every value of `key` in that case's saved states (all checkpoints, so nothing an
    older state still points at is treated as unused)."""
    refs: dict[str, set[str]] = {}
    if layout.checkpoints.exists():
        with _saver(layout) as saver:
            for item in saver.list(None):
                thread = item.config["configurable"]["thread_id"]
                refs.setdefault(thread, set()).update(_state_refs(item.checkpoint.get("channel_values", {}), key))
    return refs


def _intake_ids(layout: Layout) -> set[str]:
    if not layout.intake_memory.exists():
        return set()
    connection = sqlite3.connect(layout.intake_memory)
    try:
        return {row[0] for row in connection.execute("SELECT case_id FROM cases")}
    except sqlite3.OperationalError:
        return set()
    finally:
        connection.close()


def known_cases(layout: Layout) -> set[str]:
    """Every case ID with data anywhere (invalid-looking names are ignored, never deleted)."""
    ids = _thread_ids(layout) | _intake_ids(layout)
    for directory in layout.trace_dirs:
        ids |= {p.stem for p in directory.glob("*.jsonl")}
    if layout.output_dir.exists():
        ids |= {p.name.split("_1040sr")[0] for p in layout.output_dir.glob("*_1040sr.html")}
    return {i for i in ids if CASE_ID.fullmatch(i)}


def last_activity(layout: Layout, case_id: str) -> datetime | None:
    """The newest sign of life: latest checkpoint, Intake save, trace, draft form or audit entry."""
    case_id = _case_id(case_id)
    times = []
    if layout.checkpoints.exists():
        with _saver(layout) as saver:
            found = saver.get_tuple({"configurable": {"thread_id": case_id}})
            if found and found.checkpoint.get("ts"):
                times.append(datetime.fromisoformat(found.checkpoint["ts"].replace("Z", "+00:00")))
    if layout.intake_memory.exists():
        connection = sqlite3.connect(layout.intake_memory)
        try:
            import json

            row = connection.execute("SELECT payload FROM cases WHERE case_id=?", (case_id,)).fetchone()
            stamp = json.loads(row[0]).get("updated_at") if row else None
            if stamp:
                times.append(datetime.fromisoformat(stamp.replace("Z", "+00:00")))
        except sqlite3.OperationalError:
            pass
        finally:
            connection.close()
    files = [d / f"{_safe(case_id)}.jsonl" for d in layout.trace_dirs]
    files += list(layout.output_dir.glob(f"{_safe(case_id)}_1040sr.html")) if layout.output_dir.exists() else []
    times += [datetime.fromtimestamp(f.stat().st_mtime, timezone.utc) for f in files if f.exists()]
    audited = layout.audit.last_activity(case_id)
    if audited:
        times.append(audited)
    times = [t if t.tzinfo else t.replace(tzinfo=timezone.utc) for t in times]
    return max(times) if times else None


def purge_case(case_id: str, layout: Layout | None = None, *, actor: str = "system:retention",
               reason: str = "requested", dry_run: bool = False) -> dict:
    """Delete everything stored for one case. Returns what was (or, with dry_run, would be) removed."""
    case_id, layout = _case_id(case_id), layout or Layout()
    removed = {"checkpoints": 0, "intake_answers": 0, "document_images": 0, "uploads": 0, "traces": 0,
               "draft_forms": 0}
    own_images: set[str] = set()
    own_uploads: set[str] = set()

    if layout.checkpoints.exists():
        with _saver(layout) as saver:
            others: set[str] = set()
            other_uploads: set[str] = set()
            for item in saver.list(None):
                state = item.checkpoint.get("channel_values", {})
                if item.config["configurable"]["thread_id"] == case_id:
                    own_images |= _state_refs(state, "image_file")
                    own_uploads |= _state_refs(state, "image_ref")
                    removed["checkpoints"] += 1
                else:
                    others |= _state_refs(state, "image_file")
                    other_uploads |= _state_refs(state, "image_ref")
            own_images -= others  # another case still uses it
            own_uploads -= other_uploads
            if removed["checkpoints"] and not dry_run:
                saver.delete_thread(case_id)

    if layout.intake_memory.exists():
        connection = sqlite3.connect(layout.intake_memory)
        try:
            for table in ("answer_events", "cases"):
                count = connection.execute(f"SELECT COUNT(*) FROM {table} WHERE case_id=?", (case_id,)).fetchone()[0]
                removed["intake_answers"] += count
                if count and not dry_run:
                    connection.execute(f"DELETE FROM {table} WHERE case_id=?", (case_id,))
            connection.commit()
        except sqlite3.OperationalError:
            pass
        finally:
            connection.close()

    for name in sorted(own_images):
        image = layout.documents / name
        if Path(name).name == name and image.is_file():
            removed["document_images"] += 1
            if not dry_run:
                image.unlink()

    for handle in sorted(own_uploads):
        upload = layout.uploads / f"{handle}.png"
        if UPLOAD_HANDLE.fullmatch(handle) and upload.is_file():
            removed["uploads"] += 1
            if not dry_run:
                upload.unlink()

    for directory in layout.trace_dirs:
        trace = directory / f"{_safe(case_id)}.jsonl"
        if trace.is_file():
            removed["traces"] += 1
            if not dry_run:
                trace.unlink()
    if layout.output_dir.exists():
        for form in layout.output_dir.glob(f"{_safe(case_id)}_1040sr.html"):
            removed["draft_forms"] += 1
            if not dry_run:
                form.unlink()

    if not dry_run and any(removed.values()):
        layout.audit.record(case_id, "case_purged", actor, reason=reason, **removed)
    return {"case_id": case_id, "dry_run": dry_run, "removed": removed}


def purge_expired(layout: Layout | None = None, *, max_age_days: float = DEFAULT_RETENTION_DAYS,
                  now: datetime | None = None, actor: str = "system:retention",
                  dry_run: bool = False) -> list[dict]:
    """Purge every case idle for more than `max_age_days`. A case with no timestamp anywhere is
    left alone (it cannot be judged) and reported with `skipped`."""
    layout, now = layout or Layout(), now or datetime.now(timezone.utc)
    cutoff, results = now - timedelta(days=max_age_days), []
    for case_id in sorted(known_cases(layout)):
        seen = last_activity(layout, case_id)
        if seen is None:
            results.append({"case_id": case_id, "skipped": "no activity time found"})
        elif seen < cutoff:
            results.append(purge_case(case_id, layout, actor=actor, dry_run=dry_run,
                                      reason=f"idle more than {max_age_days:g} days"))
    return results


def purge_stale_uploads(layout: Layout | None = None, *, max_age_hours: float = STALE_UPLOAD_HOURS,
                        now: datetime | None = None, dry_run: bool = False) -> int:
    """Delete uploads older than `max_age_hours` that no case's saved state points at (an image that
    was uploaded but never saved to a case)."""
    layout, now = layout or Layout(), now or datetime.now(timezone.utc)
    cutoff, count = (now - timedelta(hours=max_age_hours)).timestamp(), 0
    in_use = set().union(*_stored_refs(layout, "image_ref").values()) if layout.checkpoints.exists() else set()
    if layout.uploads.exists():
        for upload in layout.uploads.iterdir():
            if upload.is_file() and upload.stem not in in_use and upload.stat().st_mtime < cutoff:
                count += 1
                if not dry_run:
                    upload.unlink()
    return count
