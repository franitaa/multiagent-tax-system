"""The ONE wrapper every agent call goes through (orchestrator included).

Responsibilities: build the agent's scoped view, hand it a ToolBox limited to its
allow-list, run it, enforce the write allow-list, stamp the handoff, estimate token
counts, and append one JSONL record to traces/<thread_id>.jsonl. Agents never log.

Traces store field NAMES, never values, so personal data cannot leak into them.
"""
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from langgraph.errors import GraphInterrupt

from src.orchestration.access import POLICY, AccessViolation, ToolBox
from src.orchestration.context import view_for
from src.orchestration.tokens import TOKEN_SOURCE, estimate_tokens


class Runner:
    def __init__(self, trace_dir: str | Path = "traces", scoped: bool = True):
        self.trace_dir = Path(trace_dir)
        self.scoped = scoped

    def run(self, name: str, fn: Callable, state: dict, thread_id: str) -> dict:
        view = view_for(name, state, self.scoped)
        tools = ToolBox(name)
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
            raise

        if update.get("handoff_request"):
            update["handoff_request"] = {**update["handoff_request"], "from": name}
        violations = sorted(set(update) - POLICY[name].writes)
        self._write(thread_id, self._record(*ctx, update, violations))
        if violations:
            raise AccessViolation(f"{name} wrote outside its allow-list: {violations}")
        return update

    def _record(self, thread_id, name, step, view, tools, started, update, violations) -> dict:
        return {
            "ts": datetime.now(timezone.utc).isoformat(),
            "thread_id": thread_id,
            "step": step,
            "agent": name,
            "handoff": self._handoff(name, update),
            "fields_read": sorted(view),
            "fields_written": sorted(update),
            "tools_called": tools.calls,
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
            return {"from": name, "to": entry["to"], "reason": entry["reason"]}
        request = update.get("handoff_request")
        if request:
            return {"from": name, "to": request["to"], "reason": request["reason"]}
        return {"from": name, "to": "orchestrator", "reason": "no handoff requested"}

    def _write(self, thread_id: str, record: dict) -> None:
        self.trace_dir.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", str(thread_id))
        with open(self.trace_dir / f"{safe}.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, sort_keys=True) + "\n")
