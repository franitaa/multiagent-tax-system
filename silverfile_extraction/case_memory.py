"""MEM-2/3: durable intake facts, append-only answer history, and safe resume summaries.

This store is separate from LangGraph execution checkpoints. P2 selects the next
question; P1 owns interrupts. No tax rule or conditional question is inferred here.
Use the same case ID in this store and case_config().
"""
from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .checkpointer import case_config
from .models import money_string, utc_now
from .privacy import SSN, SafeInputError, reject_non_test_ssns

QUESTION_TOPICS = {
    **{f"Q{i}": "marital and filing information" for i in range(1, 4)},
    **{f"Q{i}": "birth dates and sight" for i in range(4, 8)},
    **{f"Q{i}": "dependents" for i in range(8, 13)},
    **{f"Q{i}": "available tax documents" for i in range(13, 18)},
    **{f"Q{i}": "payments and adjustments" for i in range(18, 21)},
    **{f"Q{i}": "safety questions" for i in range(21, 24)},
}


class StaleRevisionError(ValueError):
    """Reload before saving; another browser tab or worker changed this case."""


def _question(value: str | None) -> None:
    if value is not None and not re.fullmatch(r"Q(?:[1-9]|1[0-9]|2[0-3])(?::[A-Za-z0-9_-]{1,40})?", value):
        raise SafeInputError("Use an intake question ID Q1-Q23, optionally followed by :item_id.")


def _safe_value(value, *, allow_test_ssn=False):
    encoded = json.dumps(value, allow_nan=False)
    if len(encoded) > 16000:
        raise SafeInputError("Answer is too large.")
    reject_non_test_ssns(encoded)
    if SSN.search(encoded) and not allow_test_ssn:
        raise SafeInputError("Do not save an unsolicited SSN. P2 must redact it before saving.")
    return json.loads(encoded)


class CaseMemory:
    def __init__(self, db_path: str | Path = "runtime/intake_memory.sqlite"):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS cases (
                    case_id TEXT PRIMARY KEY, revision INTEGER NOT NULL, payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS answer_events (
                    case_id TEXT NOT NULL, event_id TEXT NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY(case_id, event_id)
                );
            """)

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=15)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def _empty(case_id):
        return {"case_id": case_id, "revision": 0, "answers": {}, "answer_history": [],
                "next_question_id": "Q1", "stage": "intake", "pending_review": [], "updated_at": None}

    def _load(self, connection, case_id):
        row = connection.execute("SELECT payload FROM cases WHERE case_id=?", (case_id,)).fetchone()
        return json.loads(row[0]) if row else self._empty(case_id)

    def _save(self, connection, state):
        connection.execute("INSERT INTO cases VALUES (?, ?, ?) ON CONFLICT(case_id) DO UPDATE "
                           "SET revision=excluded.revision, payload=excluded.payload",
                           (state["case_id"], state["revision"], json.dumps(state)))

    def load_case(self, case_id: str) -> dict:
        case_config(case_id)
        with self._connect() as connection:
            return self._load(connection, case_id)

    def save_answer(self, case_id: str, question_id: str, value, *, actor: str,
                    event_id: str, next_question_id: str | None,
                    expected_revision: int, monetary: bool = False) -> dict:
        """Persist before invoking the graph. Retry with the SAME event_id.

        Re-answering creates a new event and retains the old value. Cursor and answer
        commit atomically. monetary=True requires a decimal string and attaches P5's
        five provenance fields. event_id must be a stable client-generated opaque ID.
        """
        case_config(case_id)
        _question(question_id)
        _question(next_question_id)
        if not actor.strip() or len(actor) > 80 or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", event_id):
            raise SafeInputError("Use a short actor identifier and an opaque event ID.")
        _safe_value(actor)
        base = question_id.split(":")[0]
        value = _safe_value(value, allow_test_ssn=base == "Q12")
        if base == "Q12" and (not isinstance(value, str) or
                              not re.fullmatch(r"9\d{2}-?\d{2}-?\d{4}", value)):
            raise SafeInputError("Q12 accepts only a complete synthetic 900-series SSN.")
        if base == "Q19" and not monetary:
            raise SafeInputError("Q19 is a payment amount; save it with monetary=True.")
        if monetary:
            if not isinstance(value, str):
                raise SafeInputError("Monetary answers must be decimal strings, not floats.")
            value = money_string(value)
        request = {"question_id": question_id, "value": value, "actor": actor,
                   "next_question_id": next_question_id, "monetary": monetary}
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            old = connection.execute("SELECT payload FROM answer_events WHERE case_id=? AND event_id=?",
                                     (case_id, event_id)).fetchone()
            if old:
                if json.loads(old[0])["request"] != request:
                    raise SafeInputError("This event ID already belongs to a different answer.")
                return self._load(connection, case_id)
            state = self._load(connection, case_id)
            if state["revision"] != expected_revision:
                raise StaleRevisionError("The case changed. Reload it before saving another answer.")
            now = utc_now()
            event = {"event_id": event_id, "at": now, "request": request,
                     "previous": state["answers"].get(question_id)}
            answer = {"value": value, "actor": actor, "recorded_at": now, "event_id": event_id}
            if monetary:
                answer["provenance"] = {"value": value, "formula": None, "inputs": {},
                    "source": {"type": "direct_user_input", "case_id": case_id,
                               "question_id": question_id, "event_id": event_id,
                               "entered_by": actor, "recorded_at": now}, "tool": None}
            state["answers"][question_id] = answer
            # Avoid recursively nesting old history: each event retains the prior answer only.
            state["answer_history"].append(event)
            state.update(revision=state["revision"] + 1, next_question_id=next_question_id, updated_at=now)
            connection.execute("INSERT INTO answer_events VALUES (?, ?, ?)",
                               (case_id, event_id, json.dumps(event)))
            self._save(connection, state)
            return state

    def set_progress(self, case_id: str, *, next_question_id: str | None, expected_revision: int,
                     stage: str = "intake", pending_review: list[str] | None = None) -> dict:
        """P2 can go back without deleting answers. P1 supplies unresolved review flags."""
        case_config(case_id)
        _question(next_question_id)
        if stage not in {"intake", "documents", "paused", "draft_ready"}:
            raise SafeInputError("Unsupported progress stage.")
        if pending_review is not None and (len(pending_review) > 30 or any(
                not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", flag) for flag in pending_review)):
            raise SafeInputError("Use short review codes, not free-text personal details.")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            state = self._load(connection, case_id)
            if state["revision"] != expected_revision:
                raise StaleRevisionError("Reload the current case before changing progress.")
            state.update(revision=state["revision"] + 1, next_question_id=next_question_id,
                         stage=stage, updated_at=utc_now())
            if pending_review is not None:
                state["pending_review"] = pending_review
            self._save(connection, state)
            return state

    def get_resume_context(self, case_id: str) -> dict:
        state = self.load_case(case_id)
        topics = list(dict.fromkeys(QUESTION_TOPICS[key.split(":")[0]] for key in state["answers"]))
        summary = ("Welcome back. We recorded answers about " + ", ".join(topics) + "."
                   if topics else "No intake answers have been saved yet.")
        if state["pending_review"]:
            summary += " Some information is waiting for a volunteer to review."
        if state["next_question_id"]:
            summary += " We saved your place so you can continue."
        return {"case_id": case_id, "revision": state["revision"], "summary": summary,
                "next_question_id": state["next_question_id"], "stage": state["stage"],
                "pending_review": state["pending_review"], "covered_topics": topics,
                "updated_at": state["updated_at"]}

