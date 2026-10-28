"""The ONE wrapper every agent call goes through (orchestrator included).

Responsibilities: build the agent's scoped view, hand it a ToolBox limited to its
allow-list, run it, enforce the write allow-list, stamp the handoff, estimate token
counts, and append one JSONL record to traces/<thread_id>.jsonl. Agents never log.

Traces store field NAMES, never values, so personal data cannot leak into them.
"""
import json
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from langgraph.errors import GraphInterrupt

from document_security import make_untrusted_document_payload
from security import redact_pii
from src.audit import AuditLog
from src.orchestration.access import POLICY, AccessViolation, ToolBox
from src.orchestration.context import view_for
from src.orchestration.tokens import TOKEN_SOURCE, estimate_tokens
from src.orchestration.validate import check_update
from src.state import COMPLETE, HALTED_BY_HUMAN


class Runner:
    def __init__(self, trace_dir: str | Path = "traces", scoped: bool = True, tool_registry=None,
                 audit_dir: str | Path | None = None):
        self.tool_registry = tool_registry
        self.trace_dir = Path(trace_dir)
        self.audit = AuditLog(audit_dir or self.trace_dir / "audit")
        self.scoped = scoped
        self._lock = threading.Lock()  # parallel workers write the same trace file

    def run(self, name: str, fn: Callable, state: dict, thread_id: str) -> dict:
        view = self._sanitize_documents(view_for(name, state, self.scoped))
        self._audit_flagged_documents(thread_id, name, view)
        tools = ToolBox(name, self.tool_registry)
        started = time.perf_counter()
        ctx = (thread_id, name, state.get("step", 0), view, tools, started)
        try:
            update = dict(fn(view, tools) or {})
        except GraphInterrupt:
            # The human gate paused the graph. Trace it (condition code only), then re-raise.
            condition = (view.get("escalation") or {}).get("condition")
            handoff = {"from": name, "to": "orchestrator", "reason": "paused: awaiting human decision"}
            self._write(thread_id, {**self._record(*ctx, {}, []), "handoff": handoff,
                                    "interrupted": True, "interrupted_on": condition})
            self.audit.record(thread_id, "paused_for_volunteer", f"system:{name}", condition=condition)
            raise

        if update.get("handoff_request"):
            update["handoff_request"] = {**update["handoff_request"], "from": name}
        violations = sorted(set(update) - POLICY[name].writes)
        malformed = [] if violations else check_update(name, update)
        self._write(thread_id, self._record(*ctx, update, violations + [f"invalid: {p}" for p in malformed]))
        if violations:
            raise AccessViolation(f"{name} wrote outside its allow-list: {violations}")
        if malformed:
            raise AccessViolation(f"{name} returned a malformed update: {malformed}")
        self._audit_update(thread_id, name, update)
        return update

    def _audit_flagged_documents(self, thread_id: str, name: str, view: dict) -> None:
        """One audit entry per flagged document per case, however many agents read it."""
        flagged = [d for d in view.get("documents") or [] if d.get("injection_suspected")]
        if not flagged:
            return
        with self._lock:
            logged = {e["details"].get("document") for e in self.audit.read(thread_id)
                      if e["event"] == "document_flagged"}
        for doc in flagged:
            if doc.get("id") not in logged:
                self.audit.record(thread_id, "document_flagged", f"system:{name}", document=doc.get("id"),
                                  signals=doc.get("injection_signals", []))

    def _audit_update(self, thread_id: str, name: str, update: dict) -> None:
        """Audit events for what an agent's update means for the case. No values, only names."""
        flag = update.get("escalation")
        if isinstance(flag, dict) and flag.get("pending") and not flag.get("replace"):
            self.audit.record(thread_id, "escalation_raised", f"agent:{name}",
                              condition=flag.get("condition"), document=flag.get("document_id"))
        for decision in update.get("human_decisions") or []:
            who = decision.get("reviewer") or "unidentified"
            self.audit.record(
                thread_id, "volunteer_decision", f"volunteer:{who}", condition=decision.get("condition"),
                decision=decision.get("decision"), note=decision.get("note", ""),
                resolution_fields=sorted(decision.get("resolution") or {}))
        if update.get("status") == COMPLETE:
            self.audit.record(thread_id, "draft_ready", f"agent:{name}")
        elif update.get("status") == HALTED_BY_HUMAN:
            self.audit.record(thread_id, "case_stopped", f"agent:{name}")

    @staticmethod
    def _sanitize_documents(view: dict) -> dict:
        """Document text is untrusted: redact non-test SSNs and other identifiers, and label it
        as data (not instructions) before any agent sees it. A defensive filter only."""
        docs = view.get("documents")
        if not docs:
            return view
        safe = []
        for doc in docs:
            payload = make_untrusted_document_payload(doc.get("text", ""), str(doc.get("id", "document")))
            safe.append({**doc, "text": payload["content"], "trust_level": payload["trust_level"],
                         "ssn_redacted": payload["ssn_redacted"],
                         "injection_suspected": payload["injection_suspected"],
                         "injection_signals": payload["injection_signals"]})
        clean = type(view)({**view, "documents": safe})
        clean.control = getattr(view, "control", {})  # keep the orchestrator's control inputs
        return clean

    def _record(self, thread_id, name, step, view, tools, started, update, violations) -> dict:
        return {
            "ts": datetime.now(timezone.utc).isoformat(),
            "thread_id": thread_id,
            "step": step,
            "agent": name,
            "handoff": self._handoff(name, update),
            "fields_read": sorted(view),
            "control_fields_read": sorted(getattr(view, "control", {})),
            "fields_written": sorted(update),
            "tools_called": tools.calls,
            "tool_transports": sorted(set(tools.transports)),
            "duration_ms": round((time.perf_counter() - started) * 1000, 3),
            "input_tokens": estimate_tokens(view),
            "output_tokens": estimate_tokens(update),
            "token_source": TOKEN_SOURCE,
            "context_mode": "scoped" if self.scoped else "full",
            "violations": violations,
        }

    @staticmethod
    def _handoff(name: str, update: dict) -> dict:
        if name == "orchestrator":
            entry = update["handoff_log"][-1]
            return {"from": name, "to": entry["to"], "reason": redact_pii(str(entry["reason"]))}
        request = update.get("handoff_request")
        if request:
            # tolerant: a malformed request is rejected by check_update right after this is traced
            return {"from": name, "to": request.get("to") if isinstance(request, dict) else None,
                    "reason": redact_pii(str(request.get("reason", ""))) if isinstance(request, dict) else ""}
        return {"from": name, "to": "orchestrator", "reason": "no handoff requested"}

    def _write(self, thread_id: str, record: dict) -> None:
        self.trace_dir.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", str(thread_id))
        line = json.dumps(record, sort_keys=True) + "\n"
        with self._lock, open(self.trace_dir / f"{safe}.jsonl", "a", encoding="utf-8") as fh:
            fh.write(line)
