"""Volunteer dashboard logic (Kushim). Owner: Supriya Patil.

SUMMARY FOR THE TEAM
In one line: everything the volunteer dashboard needs, without any web code, so it can be tested.

What it does:
  - Lists every saved case (the same saved-sessions file as the taxpayer chat page), each with
    the taxpayer's name, a status in words ("Needs a volunteer", "Answering questions",
    "Draft ready", "Stopped"), what the alarm is about, and when it was last active.
    Cases that need a volunteer come first. "Quiet" requests that do not pause the chat
    ("I'm not sure", "Talk to a volunteer", an answer not understood 3 times) are shown too,
    so nobody who asked for a person is missed.
  - For one case: the alarm in plain words, the reason, the taxpayer's own words from the
    volunteer notes, their answers so far, and the choices the volunteer is allowed.
  - Resolves an alarm by passing the volunteer's decision to Francesca's human gate
    (src/orchestration/human.py) unchanged. The gate decides what is allowed (e.g. pressure or
    exploitation can only be stopped) and checks the answer; if it is not valid, its message
    is returned so the page can show it and the volunteer can try again. The volunteer's name
    is required, so the record always shows who decided. Before saving it checks that the case
    is still waiting for the same alarm (two volunteers on one case: the second is told, not
    shown "saved"), and that "continue" on a filing-status alarm comes with a chosen status.
  - Case history from Sahana's audit log (src/audit.py): who did what and when, with its
    tamper check; opening a case is recorded as "viewed", as the audit log asks.
  - Answers with any SSN shown as •••-••-1234, and the draft form when there is one.

What is still missing:
  - Approving a W-2 reading (EXTRACTION_REVIEW) is done on JiWon's W-2 page, not here; the
    dashboard shows the case as paused and says where to go (W2_PAGE_HELP).
  - Cases started on the W-2 page (IDs not like SF-123-456) are listed too, named
    "(test case from the W-2 page)", so a volunteer can tell them apart.
  - No login: the volunteer's name is NOT verified (anyone can type any name, and the audit log
    records it as typed), and anyone who has the address can open the dashboard and read
    every case. Fine for a classroom demo with test data only; a staff passcode is a team
    decision for later.
"""
import re
from datetime import datetime, timezone
from pathlib import Path

from langgraph.types import Command

from src import state as S
from src.agents import intake_agent
from src.audit import AuditLog
from src.orchestration.human import FILING_STATUSES, UNCERTAIN_ANSWERS
from src.ui import chat_session as chat

TRACE_DIR = "traces"  # the chat page's default too, so both write the same audit log (traces/audit)

# Status in words, in the order the dashboard lists them.
NEEDS_VOLUNTEER = "Needs a volunteer"
ANSWERING = "Answering questions"
DRAFT_READY = "Draft ready"
STOPPED = "Stopped"
STATUS_ORDER = (NEEDS_VOLUNTEER, ANSWERING, DRAFT_READY, STOPPED)

# What each alarm means, in plain words for the volunteer.
ALARMS = {
    S.TAX_ADVICE_REQUEST: "The taxpayer asked for tax advice.",
    S.FILING_STATUS_AMBIGUITY: "The filing status is unclear (for example, a spouse died during the year).",
    S.EXPLOITATION_SIGNS: "Possible pressure from someone else, or a refund account the taxpayer cannot describe.",
    S.OUT_OF_SCOPE: "Something on this return is outside what SilverFile can prepare.",
    S.SOURCE_CONFLICT: "An answer does not match a tax document.",
    S.FORM_1099R_BOX_2B: "A 1099-R says the taxable amount was not determined (box 2b).",
    S.ANSWER_UNCERTAIN: "The taxpayer was not sure about an answer the return needs.",
    S.EXTRACTION_REVIEW: "A W-2 reading needs to be checked (on the W-2 page).",
    S.LOOP_GUARD: "The system went round in circles and stopped itself.",
    S.REVIEW_BOUND_EXCEEDED: "The final check kept failing and stopped itself.",
    S.ELIGIBILITY_UNDECIDED: "The rules could not decide the filing status or eligibility.",
    S.INCOME_NOT_READ: "The taxpayer has an income form, but no amount from it reached the draft.",
}

# Plain words for the filing statuses the gate accepts.
FILING_STATUS_WORDS = {
    "single": "Single",
    "married_filing_jointly": "Married filing jointly",
    "married_filing_separately": "Married filing separately",
    "head_of_household": "Head of household",
    "qualifying_surviving_spouse": "Qualifying surviving spouse",
}


# Why some alarms offer only "Stop" (the gate's rule), so the volunteer does not look for a
# missing button.
W2_PAGE_HELP = ("This W-2 reading cannot be approved in this dashboard yet. Open JiWon's W-2 page "
                "(app.py; see the README), enter this case ID, compare the amounts with the W-2 image "
                "and save the review there. Until then this case stays paused.")
STOP_ONLY_WHY = ("For this alarm the only choice is to stop the case: SilverFile cannot prepare it, "
                 "and a volunteer cannot take responsibility for continuing it here.")

# Audit-log events in words, for the case history.
EVENT_WORDS = {
    "escalation_raised": "Alarm raised",
    "paused_for_volunteer": "Paused for a volunteer",
    "volunteer_decision": "Volunteer decided",
    "viewed": "Opened in the dashboard",
    "document_flagged": "Document flagged",
    "draft_ready": "Draft form ready",
    "draft_form_written": "Draft form saved",
    "case_stopped": "Case stopped",
    "case_purged": "Case deleted",
    "halted_by_error": "Stopped on an error",
}


def open_graph():
    """The same graph and saved-sessions file as the taxpayer chat page."""
    return chat.make_graph(chat.open_saved_sessions(), trace_dir=TRACE_DIR)


def _audit() -> AuditLog:
    return AuditLog(Path(TRACE_DIR) / "audit")


def _config(case_id: str) -> dict:
    return {"configurable": {"thread_id": case_id}}


def case_ids(graph) -> list[str]:
    """Every case in the saved-sessions file."""
    return sorted({c.config["configurable"]["thread_id"] for c in graph.checkpointer.list(None)})


def pending(graph, case_id: str) -> dict | None:
    """What the human gate is waiting for: condition, reason, options, resolution_fields and,
    after an invalid answer, "error". None if the case is not waiting for a volunteer."""
    interrupts = graph.get_state(_config(case_id)).interrupts
    return dict(interrupts[0].value) if interrupts else None


def _status(graph, case_id: str) -> str:
    return {chat.WAITING_FOR_VOLUNTEER: NEEDS_VOLUNTEER, chat.STOPPED: STOPPED,
            chat.FINISHED: DRAFT_READY}.get(chat.screen(graph, case_id), ANSWERING)


# Notes that do not pause the chat but still need a volunteer: "I'm not sure", "Talk to a
# volunteer", and an answer not understood three times. Alarm notes are handled by the pause.
_QUIET_REASONS = (intake_agent.REASON_NOT_SURE, intake_agent.REASON_ASKED, intake_agent.REASON_STUCK)


def _open_questions(facts: dict) -> list[dict]:
    notes = (facts.get(intake_agent.NOTES) or {}).get("value") or []
    return [n for n in notes if n.get("reason") in _QUIET_REASONS and not n.get("resolved")]


def open_questions_text(row: dict) -> str:
    """e.g. "Asked to talk to a volunteer; 2 answers marked "not sure"", or "" if none."""
    parts = []
    if row["asked_for_volunteer"]:
        parts.append("Asked to talk to a volunteer")
    others = row["open_questions"] - row["asked_for_volunteer"]
    if others:
        parts.append(f"{others} answer{'s' if others > 1 else ''} for a volunteer to check")
    return "; ".join(parts)


def case_summary(graph, case_id: str) -> dict:
    """One row of the case list."""
    snapshot = graph.get_state(_config(case_id))
    facts = snapshot.values.get("facts", {})
    waiting = pending(graph, case_id)
    condition = waiting["condition"] if waiting else None
    quiet = _open_questions(facts)
    from_chat_page = chat.clean_case_id(case_id) == case_id  # SF-123-456; others come from test pages
    return {
        "case_id": case_id,
        "name": (facts.get("taxpayer_name") or {}).get("value")
                or ("(no name yet)" if from_chat_page else "(test case from the W-2 page)"),
        "status": _status(graph, case_id),
        "condition": condition,
        "alarm": ALARMS.get(condition, condition or ""),
        "open_questions": len(quiet),
        "asked_for_volunteer": int(any(n["reason"] == intake_agent.REASON_ASKED for n in quiet)),
        "last_active": snapshot.created_at,
    }


def all_cases(graph) -> list[dict]:
    """Every case: those paused for a volunteer first; within each status, people who asked for a
    volunteer, then those with open questions, then the most recently active."""
    rows = [case_summary(graph, case_id) for case_id in case_ids(graph)]
    rows.sort(key=lambda r: r["last_active"] or "", reverse=True)
    return sorted(rows, key=lambda r: (STATUS_ORDER.index(r["status"]), -r["asked_for_volunteer"],
                                       -r["open_questions"]))


OPEN_QUESTIONS = "Open questions"  # cases with notes for a volunteer, whatever their status


def counts(rows: list[dict]) -> dict:
    """How many cases are in each status, plus how many have open questions for a volunteer."""
    result = {status: sum(1 for r in rows if r["status"] == status) for status in STATUS_ORDER}
    result[OPEN_QUESTIONS] = sum(1 for r in rows if r["open_questions"])
    return result


# Short names for the "what volunteers are needed for" chart.
NEED_WORDS = {
    S.TAX_ADVICE_REQUEST: "Tax advice question", S.FILING_STATUS_AMBIGUITY: "Filing status unclear",
    S.EXPLOITATION_SIGNS: "Possible pressure", S.OUT_OF_SCOPE: "Out of scope",
    S.SOURCE_CONFLICT: "Answer vs document", S.FORM_1099R_BOX_2B: "1099-R box 2b",
    S.ANSWER_UNCERTAIN: "Unsure answer", S.EXTRACTION_REVIEW: "W-2 check",
    S.INCOME_NOT_READ: "Income form not read",
}
OTHER_NEED = "Other"
QUIET_NEED = "Asked for a person / not sure"


def needs_breakdown(rows: list[dict]) -> dict:
    """What volunteers are needed for right now, e.g. {"Tax advice question": 2, ...}: each paused
    case by its alarm, plus cases with only quiet requests. Largest first."""
    result = {}
    for row in rows:
        if row["condition"]:
            need = NEED_WORDS.get(row["condition"], OTHER_NEED)
        elif row["open_questions"]:
            need = QUIET_NEED
        else:
            continue
        result[need] = result.get(need, 0) + 1
    return dict(sorted(result.items(), key=lambda item: -item[1]))


def matches(row: dict, show: str, search: str) -> bool:
    """Filter for the case list: a status (or "Open questions", or "All") and a search on ID or name."""
    if show == OPEN_QUESTIONS and not row["open_questions"]:
        return False
    if show not in ("All", OPEN_QUESTIONS) and row["status"] != show:
        return False
    text = search.strip().lower()
    return not text or text in row["case_id"].lower() or text in row["name"].lower()


def time_ago(iso: str | None, now: datetime | None = None) -> str:
    """"5 minutes ago", "2 hours ago", "3 days ago"."""
    if not iso:
        return ""
    seconds = ((now or datetime.now(timezone.utc)) - datetime.fromisoformat(iso)).total_seconds()
    for size, unit in ((86400, "day"), (3600, "hour"), (60, "minute")):
        if seconds >= size:
            n = int(seconds // size)
            return f"{n} {unit}{'s' if n > 1 else ''} ago"
    return "just now"


def volunteer_notes(graph, case_id: str) -> list[dict]:
    """Intake's notes for the volunteer: open "not sure" questions and the taxpayer's own words
    when an alarm was raised (real-looking SSNs were already removed)."""
    facts = graph.get_state(_config(case_id)).values.get("facts", {})
    return list((facts.get(intake_agent.NOTES) or {}).get("value") or [])


_SSN = re.compile(r"\b\d{3}-?\d{2}-?(\d{4})\b")


def answers(graph, case_id: str) -> list[dict]:
    """The taxpayer's answers, with any SSN shown as •••-••-1234 (only practice numbers are ever
    saved, but a staff screen should not show full numbers)."""
    return [{**row, "answer": _SSN.sub(r"•••-••-\1", str(row["answer"]))}
            for row in chat.answers(graph, case_id)]


def draft_form_html(graph, case_id: str) -> str | None:
    """The draft 1040-SR with click-to-see sources, or None if nothing is computed yet."""
    return chat.draft_form_html(graph, case_id)


def history(case_id: str) -> list[dict]:
    """The case's audit log in words: [{"when", "who", "what", "detail"}], oldest first.
    The log never holds answers or amounts; notes in it are already redacted."""
    rows = []
    for entry in _audit().read(case_id):
        details = entry.get("details") or {}
        detail = " · ".join(str(details[k]) for k in ("condition", "decision", "note") if details.get(k))
        rows.append({"when": entry["ts"], "who": entry["actor"],
                     "what": EVENT_WORDS.get(entry["event"], entry["event"]), "detail": detail})
    return rows


def history_intact(case_id: str) -> bool:
    """True if nobody has edited or removed entries in the middle of the audit log."""
    return not _audit().verify(case_id)


def record_view(case_id: str, volunteer: str) -> None:
    """Audit: a volunteer opened this case (src/audit.py asks the dashboard to record this)."""
    _audit().record(case_id, "viewed", f"volunteer:{volunteer}")


def choices(waiting: dict) -> dict | None:
    """The values a volunteer may pick for the fact the gate asks about, as {value: words},
    or None when the volunteer types it (a document conflict) or nothing is needed."""
    fields = waiting.get("resolution_fields") or []
    if waiting["condition"] == S.FILING_STATUS_AMBIGUITY:
        return dict(FILING_STATUS_WORDS)
    if waiting["condition"] == S.ANSWER_UNCERTAIN and fields:
        return {value: value.replace("_", " ").capitalize() for value in UNCERTAIN_ANSWERS.get(fields[0], ())}
    return None


NO_LONGER_WAITING = "This case is no longer waiting for a decision. Please reload."
CHOOSE_STATUS = "Choose the filing status to continue."


def resolve(graph, case_id: str, decision: str, note: str, reviewer: str,
            resolution: dict | None = None, condition: str | None = None) -> str | None:
    """Send the volunteer's decision to the human gate. Returns a message if the answer was not
    accepted (the case keeps waiting), or None when it was. The runner writes the decision to the
    audit log with the volunteer's name.

    Checked here first: the case is still waiting, and for the alarm the volunteer was looking at
    (`condition`), so a second volunteer on the same case is told instead of seeing "saved"; and
    "continue" on a filing-status alarm needs a chosen status (the gate alone would accept it)."""
    if not reviewer.strip():
        return "Please type your name first, so the record shows who decided."
    waiting = pending(graph, case_id)
    if not waiting or (condition and waiting["condition"] != condition):
        return NO_LONGER_WAITING
    if (waiting["condition"] == S.FILING_STATUS_AMBIGUITY and decision == "continue"
            and not (resolution or {}).get("filing_status")):
        return CHOOSE_STATUS
    answer = {"decision": decision, "note": note, "reviewer": reviewer.strip()}
    if resolution:
        answer["resolution"] = resolution
    graph.invoke(Command(resume=answer), _config(case_id))
    still_waiting = pending(graph, case_id)
    return still_waiting.get("error") if still_waiting else None
