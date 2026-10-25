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
        update = dict(fn(view, tools) or {})
        duration_ms = round((time.perf_counter() - started) * 1000, 3)

        if update.get("handoff_request"):
            update["handoff_request"] = {**update["handoff_request"], "from": name}
        violations = sorted(set(update) - POLICY[name].writes)

        self._write(
            thread_id,
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "thread_id": thread_id,
                "step": state.get("step", 0),
                "agent": name,
                "handoff": self._handoff(name, update),
                "fields_read": sorted(view),
                "fields_written": sorted(update),
                "tools_called": tools.calls,
                "duration_ms": duration_ms,
                "input_tokens": estimate_tokens(view),
                "output_tokens": estimate_tokens(update),
                "token_source": TOKEN_SOURCE,
                "context_mode": "scoped" if self.scoped else "full",
                "violations": violations,
            },
        )
        if violations:
            raise AccessViolation(f"{name} wrote outside its allow-list: {violations}")
        return update

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
