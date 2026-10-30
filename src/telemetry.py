"""Telemetry: what the traces and the audit log say about how the system behaved.

Read-only. Plain functions over a trace directory (`traces/<thread>.jsonl` and `traces/audit/<case>.jsonl`)
that return plain dicts and lists, so the dashboard page only draws them. Nothing here writes a file,
calls a tool or a model, or reads a value: traces hold field names and the audit log holds events and
actors, never answers or amounts (src/audit.py), and this module only counts and orders them.
Spec: docs/telemetry-dashboard-spec.md.

A line that cannot be read is skipped and counted (`unreadable_lines`), so one damaged file never
hides the rest. A missing value stays None; it is never turned into zero.
"""
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from src.audit import AuditLog
from src.tax_tools import TAX_TOOLS

COMPLETE, STOPPED, HALTED, WAITING, OPEN = (
    "complete", "stopped_by_human", "halted_by_error", "awaiting_volunteer", "open")
# The audit events that end a case, and the outcome each means.
_ENDS = {"draft_ready": COMPLETE, "case_stopped": STOPPED, "halted_by_error": HALTED}
MAX_REASON_CHARS = 120


def _safe(name) -> str:
    """The audit log's file naming, so a thread ID finds its case."""
    return re.sub(r"[^A-Za-z0-9_.-]", "_", str(name))


def _when(ts):
    try:
        return datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return None


def _seconds(start, end):
    a, b = _when(start), _when(end)
    return round((b - a).total_seconds(), 3) if a and b else None


def _read_jsonl(path: Path):
    """(rows, unreadable): every JSON object in the file, and how many lines were not one."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return [], 1
    rows, bad = [], 0
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            bad += 1
            continue
        if isinstance(row, dict):
            rows.append(row)
        else:
            bad += 1
    return rows, bad


class Snapshot:
    """Everything under one trace directory, read once."""

    def __init__(self, trace_dir="traces"):
        self.trace_dir = Path(trace_dir)
        self.unreadable_lines = 0
        self.runs: dict[str, list[dict]] = {}    # thread id -> agent calls, oldest first
        self.audit: dict[str, list[dict]] = {}   # audit key (safe case id) -> entries, in order
        self._audit_log = AuditLog(self.trace_dir / "audit")
        for path in sorted(self.trace_dir.glob("*.jsonl")):
            rows, bad = _read_jsonl(path)
            self.unreadable_lines += bad
            if rows:
                thread = str(rows[0].get("thread_id") or path.stem)
                # parallel workers write one file in finishing order; time then step orders the run
                self.runs[thread] = sorted(rows, key=lambda r: (str(r.get("ts", "")), r.get("step") or 0))
        for path in sorted((self.trace_dir / "audit").glob("*.jsonl")):
            rows, bad = _read_jsonl(path)
            self.unreadable_lines += bad
            self.audit[path.stem] = rows

    def entries(self, thread) -> list[dict]:
        return self.audit.get(_safe(thread), [])

    def cases(self) -> list[str]:
        """Every thread that left a trace, plus every audited case that has none."""
        known = {_safe(t) for t in self.runs}
        return sorted(self.runs) + sorted(key for key in self.audit if key not in known)


def _outcome(entries, records) -> str:
    ended = [_ENDS[e["event"]] for e in entries if e.get("event") in _ENDS]
    if ended:
        return ended[-1]
    if any(r.get("error") for r in records):  # a clean halt is also written to the trace
        return HALTED
    last_pause = max((i for i, e in enumerate(entries) if e.get("event") == "paused_for_volunteer"), default=-1)
    last_decision = max((i for i, e in enumerate(entries) if e.get("event") == "volunteer_decision"), default=-1)
    return WAITING if last_pause > last_decision else OPEN


def _tokens(records):
    """(input, output, sources). None if no call reported a count."""
    given = [r for r in records if isinstance(r.get("input_tokens"), (int, float))]
    if not given:
        return None, None, []
    return (sum(r["input_tokens"] for r in given),
            sum(r.get("output_tokens") or 0 for r in given),
            sorted({str(r.get("token_source")) for r in given}))


def _review_rounds(records) -> int:
    return sum(1 for r in records
               if r.get("agent") == "review" and (r.get("handoff") or {}).get("to") == "computation")


def _alerts_for(thread, records, entries):
    out = []
    for r in records:
        where = {"thread_id": thread, "step": r.get("step"), "agent": r.get("agent")}
        if r.get("violations"):
            out.append({**where, "kind": "access_violation", "detail": "; ".join(map(str, r["violations"]))})
        called = set(r.get("tools_called") or []) & set(TAX_TOOLS)
        if called and "local" in (r.get("tool_transports") or []):
            out.append({**where, "kind": "local_tax_tool", "detail": ", ".join(sorted(called))})
        if r.get("error"):
            out.append({**where, "kind": "halted_by_error", "detail": str(r["error"])})
    for e in entries:
        if e.get("event") == "document_flagged":
            out.append({"thread_id": thread, "step": None, "agent": str(e.get("actor", "")),
                        "kind": "document_flagged", "detail": "possible instructions hidden in a document"})
    return out


# ---- panels ------------------------------------------------------------------------------------


def runs(s: Snapshot) -> list[dict]:
    """One row per case: outcome, calls, wall time, tokens, escalations, review rounds, alerts."""
    rows = []
    for thread in s.cases():
        records, entries = s.runs.get(thread, []), s.entries(thread)
        tokens_in, tokens_out, sources = _tokens(records)
        first = records[0].get("ts") if records else (entries[0].get("ts") if entries else None)
        last = records[-1].get("ts") if records else (entries[-1].get("ts") if entries else None)
        rows.append({
            "case_id": thread,
            "outcome": _outcome(entries, records),
            "agent_calls": sum(1 for r in records if r.get("agent") != "orchestrator"),
            "calls": len(records),
            "started": first,
            "seconds": _seconds(first, last),
            "input_tokens": tokens_in, "output_tokens": tokens_out, "token_sources": sources,
            "escalations": [e.get("details", {}).get("condition") for e in entries
                            if e.get("event") == "escalation_raised"],
            "review_rounds": _review_rounds(records),
            "alerts": len(_alerts_for(thread, records, entries)),
        })
    return rows


def timeline(s: Snapshot, thread) -> list[dict]:
    """The calls of one case in order: who ran, how long, where control went and why."""
    out = []
    for r in s.runs.get(thread, []):
        handoff = r.get("handoff") or {}
        out.append({
            "step": r.get("step"), "agent": r.get("agent"), "ts": r.get("ts"),
            "duration_ms": r.get("duration_ms"),
            "to": handoff.get("to"), "reason": str(handoff.get("reason", ""))[:MAX_REASON_CHARS],
            "tools": list(r.get("tools_called") or []), "transports": list(r.get("tool_transports") or []),
            "paused_for_volunteer": bool(r.get("interrupted")),
            "violations": list(r.get("violations") or []), "error": r.get("error"),
        })
    return out


def agents(s: Snapshot) -> list[dict]:
    """Per agent: calls, durations, and tokens split into estimated and reported by the provider."""
    by: dict[str, dict] = defaultdict(lambda: {"calls": 0, "durations": [], "input_estimated": 0,
                                               "input_reported": 0, "output_estimated": 0, "output_reported": 0})
    for records in s.runs.values():
        for r in records:
            row = by[str(r.get("agent"))]
            row["calls"] += 1
            if isinstance(r.get("duration_ms"), (int, float)):
                row["durations"].append(r["duration_ms"])
            kind = "estimated" if r.get("token_source") == "estimate" else "reported"
            for field in ("input", "output"):
                value = r.get(f"{field}_tokens")
                if isinstance(value, (int, float)):
                    row[f"{field}_{kind}"] += value
    return [{"agent": name, "calls": row["calls"],
             "avg_ms": round(sum(row["durations"]) / len(row["durations"]), 3) if row["durations"] else None,
             "max_ms": max(row["durations"]) if row["durations"] else None,
             **{k: row[k] for k in ("input_estimated", "input_reported", "output_estimated", "output_reported")}}
            for name, row in sorted(by.items())]


def escalations(s: Snapshot) -> list[dict]:
    """Per condition: raised, how each ended, and the average time a volunteer took. Rows only for
    conditions that occurred."""
    raised, decided = Counter(), defaultdict(Counter)
    waits = defaultdict(list)
    for key, entries in s.audit.items():
        pending = {}
        for e in entries:
            details = e.get("details") or {}
            condition = details.get("condition")
            if e.get("event") == "escalation_raised":
                raised[condition] += 1
            elif e.get("event") == "paused_for_volunteer":
                pending[condition] = e.get("ts")
            elif e.get("event") == "volunteer_decision":
                decided[condition][str(details.get("decision"))] += 1
                wait = _seconds(pending.pop(condition, None), e.get("ts"))
                if wait is not None:
                    waits[condition].append(wait)
    rows = []
    for condition in sorted(set(raised) | set(decided), key=str):
        times = waits[condition]
        rows.append({"condition": condition, "raised": raised[condition],
                     "continued": decided[condition]["continue"], "stopped": decided[condition]["stop"],
                     "avg_wait_seconds": round(sum(times) / len(times), 3) if times else None})
    return rows


def review_loop(s: Snapshot) -> dict:
    """Runs where Review sent the draft back to Computation, and how many hit the bound."""
    rounds = {t: _review_rounds(r) for t, r in s.runs.items()}
    rounds = {t: n for t, n in rounds.items() if n}
    exceeded = sum(1 for entries in s.audit.values() for e in entries
                   if e.get("event") == "escalation_raised"
                   and (e.get("details") or {}).get("condition") == "REVIEW_BOUND_EXCEEDED")
    return {"runs_with_send_back": len(rounds), "rounds": rounds, "bound_exceeded": exceeded}


def safety(s: Snapshot) -> list[dict]:
    """Things that should never happen, each as {kind, case/thread, step, agent, detail}. Empty is good."""
    out = []
    for thread in s.cases():
        out.extend(_alerts_for(thread, s.runs.get(thread, []), s.entries(thread)))
    return out


def integrity(s: Snapshot) -> list[dict]:
    """The audit log's tamper check for every audited case."""
    rows = []
    for key, entries in sorted(s.audit.items()):
        try:
            problems = s._audit_log.verify(key)
            readable = True
        except ValueError:  # a line that is not JSON
            problems, readable = ["a line in the log cannot be read"], False
        rows.append({"case_id": key, "entries": len(entries), "intact": not problems and readable,
                     "problems": problems, "last_event": entries[-1].get("event") if entries else None})
    return rows


def overview(s: Snapshot) -> dict:
    rows = runs(s)
    volunteer = [r for r in rows if r["escalations"]]
    return {
        "cases": len(rows),
        "by_outcome": dict(Counter(r["outcome"] for r in rows)),
        "needed_a_volunteer": len(volunteer),
        "share_needing_a_volunteer": round(len(volunteer) / len(rows), 3) if rows else None,
        "alerts": len(safety(s)),
        "broken_chains": sum(1 for r in integrity(s) if not r["intact"]),
        "unreadable_lines": s.unreadable_lines,
    }
