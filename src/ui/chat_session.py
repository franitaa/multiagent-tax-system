"""Chat logic for the taxpayer chat page (card INT-6). Owner: Supriya Patil.

SUMMARY FOR THE TEAM
In one line: everything the chat page needs, without any web code, so it can be tested
and reused if we switch from Streamlit to another tool.

What it does:
  - Creates an easy-to-read case ID (e.g. SF-482-735) and uses it as the LangGraph
    thread_id, so a session can be continued later by typing the case ID (agreed with Shruti).
  - Sends the taxpayer's message into the graph, one graph call per message, as the
    handoff contract describes. Any real-looking SSN is removed BEFORE the message enters
    the graph, so it is never stored or logged. Practice numbers (900-999) are kept
    because Intake needs them for dependents (per the 900-999 test-SSN rule).
  - Tells the page what to show: waiting for an answer, waiting for a volunteer (no new
    messages accepted, as the contract asks), finished, or stopped by a volunteer.
  - Gives a "welcome back, so far we've covered..." summary when a session is continued.
  - Lists "Your answers so far"; each has a Change button that jumps straight to that question.
  - The conversation is split into 6 parts like an application form: `overview()` gives each
    part's status in words, and `question_label()` gives "Part 2 of 6, Question 2.3".
  - For date questions, the page shows Month / Day / Year boxes (`MONTH_OPTIONS`,
    `date_answer`), so day-first vs month-first can never be mixed up.
  - When the case is finished, `draft_form_html()` gives the draft 1040-SR page (Sahana's
    PRV-3), where every amount opens to its formula, inputs and source. None until something
    is computed, and a line without a source is never shown.
  - Sessions are saved on disk (`open_saved_sessions()`, JiWon's SQLite checkpointer), so a
    session stopped on Tuesday continues on Friday, even if the app restarted in between.
    It is the team's shared file, runtime/team_checkpoints.sqlite (not in git), which
    Sahana's retention tool also cleans up. Real-looking SSNs never reach it.
  - W-2 photo (P1 of the team's to-do list): `make_app_service()` builds JiWon's shared W-2
    service (src/p3/shared_service.py) on the saved sessions; the chat page and the volunteer
    dashboard use its graph, so a W-2 reading can be read and approved on the same case.
    After "yes" to the W-2 question, `waiting_for_w2()` makes the next screen ask only for the
    photo, until it is added or the taxpayer presses "I don't have it now" (agreed with
    Francesca and JiWon); `show_w2_upload()` lets another W-2 be added until the questions end
    (JiWon's rule: no upload after that). `add_w2()` adds a W-2 photo confirmed as not a real
    tax form; the photo is read when the questions end.
    Which AI reads it: the key in .env (OpenAI first, then Anthropic), read from the file only,
    never put in state or traces (`photo_reader()`). No key: the page says a volunteer will help.
  - If reading the photo fails (no internet, a rejected key), the case is not lost: `screen()`
    says READING_FAILED and `try_again()` carries on from where it stopped. While the photo is
    being read, `screen()` says READING (not a failure; `running()` marks the case, and an extra
    click or a second tab is ignored), and the cause of a real failure is logged
    (`note_reading_failure()`: error type and a short message, never a key).

What is still missing:
  - Nothing deletes old sessions on a timer: run Sahana's `python -m scripts.purge_cases
    --expired` on a schedule.
"""
import calendar
import logging
import re
import secrets
import threading
from contextlib import ExitStack, contextmanager

from dotenv import dotenv_values

from silverfile_extraction.checkpointer import sqlite_checkpointer
from silverfile_extraction.privacy import SafeInputError
from silverfile_extraction.vision import VisionReader
from src.agents import intake_agent, live_agents
from src.draft_form import render_draft_html
from src.graph import build_graph
from src.p3.shared_service import make_shared_service

# What the page should show
ASKING = "asking"  # a question is waiting for the taxpayer's answer
WAITING_FOR_VOLUNTEER = "waiting_for_volunteer"
FINISHED = "finished"
STOPPED = "stopped"
READING_FAILED = "reading_failed"  # the case stopped part-way (e.g. the W-2 photo could not be read)
READING = "reading"  # a step is running right now (e.g. the W-2 photo is being read): not a failure

_CASE_ID = re.compile(r"^SF-\d{3}-\d{3}$")


def new_case_id() -> str:
    """A short ID that is easy to read aloud and write down, e.g. SF-482-735."""
    digits = f"{secrets.randbelow(10**6):06d}"
    return f"SF-{digits[:3]}-{digits[3:]}"


def clean_case_id(text: str) -> str | None:
    """Accepts "sf 482 735", "SF482735", "482-735"; returns "SF-482-735" or None."""
    letters = re.sub(r"[^a-z]", "", (text or "").lower())
    digits = re.sub(r"\D", "", text or "")
    if letters not in ("", "sf") or len(digits) != 6:
        return None
    case_id = f"SF-{digits[:3]}-{digits[3:]}"
    return case_id if _CASE_ID.match(case_id) else None


SAVED_SESSIONS_FILE = "runtime/team_checkpoints.sqlite"  # the team's shared file (MEM-1)
_KEEP_OPEN = ExitStack()  # holds each saver open; without it the file closes straight away


def open_saved_sessions(path=None):
    """JiWon's SQLite checkpointer, kept open while the app runs, so sessions survive a restart."""
    return _KEEP_OPEN.enter_context(sqlite_checkpointer(path or SAVED_SESSIONS_FILE))


def make_graph(checkpointer=None, trace_dir="traces"):
    """The SilverFile graph with the real Intake. Without a checkpointer, sessions live in memory."""
    return build_graph(checkpointer, trace_dir=trace_dir, agents=live_agents())


ENV_FILE = ".env"  # API keys live only in this file (never in the repo, state or traces)
RUNTIME = "runtime"  # where JiWon's service keeps confirmed W-2 photos (not in git)
# (provider, key name, model name) in the order they are tried
_PROVIDERS = (("openai", "OPENAI_API_KEY", "OPENAI_MODEL"), ("anthropic", "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL"))


def photo_reader(env_file=None):
    """JiWon's VisionReader for the first provider with a key in .env, or None when there is no
    usable key (the page then says a volunteer will help). The key is read from the file only."""
    values = dotenv_values(env_file or ENV_FILE, interpolate=False)
    for provider, key_name, model_name in _PROVIDERS:
        key = (values.get(key_name) or "").strip()
        if key:
            try:
                return VisionReader(key, (values.get(model_name) or "").strip() or None, provider=provider)
            except SafeInputError:  # e.g. a Claude key under OPENAI_API_KEY
                return None
    return None


def make_app_service(trace_dir="traces", reader=None, saved_sessions=None):
    """JiWon's shared W-2 service on the saved sessions. Use its `.graph` for every chat and
    dashboard call, so the W-2 tools are there when a photo is read or approved."""
    return make_shared_service(saved_sessions or open_saved_sessions(), runtime=RUNTIME,
                               reader=reader if reader is not None else photo_reader(), trace_dir=trace_dir)


def _config(case_id: str) -> dict:
    return {"configurable": {"thread_id": case_id}}


def exists(graph, case_id: str) -> bool:
    return bool(graph.get_state(_config(case_id)).values)


def start(graph, case_id: str) -> None:
    """Begin a new session: Intake says hello and asks the first question."""
    graph.invoke({"case_id": case_id}, _config(case_id))


def clean_message(text: str) -> str:
    """Remove real-looking SSNs before the message enters the graph; keep practice numbers."""
    return intake_agent.redact_ssn(text.strip())


_RUNNING: set[str] = set()  # cases whose graph is running in this app right now
_RUNNING_LOCK = threading.Lock()


@contextmanager
def running(case_id: str):
    """Claim a case while the graph works on it; yields False if another run already has it, so a
    second click or tab cannot start a second run (the check and the claim are one step). Reading a
    W-2 photo takes several seconds; a page run in that time must show "we are reading", not
    "we couldn't read"."""
    with _RUNNING_LOCK:
        claimed = case_id not in _RUNNING
        if claimed:
            _RUNNING.add(case_id)
    try:
        yield claimed
    finally:
        if claimed:
            with _RUNNING_LOCK:
                _RUNNING.discard(case_id)


def is_running(case_id: str) -> bool:
    with _RUNNING_LOCK:
        return case_id in _RUNNING


def send(graph, case_id: str, text: str) -> None:
    """Send one taxpayer message. Ignored while a volunteer is needed, the case is over, or the
    previous answer is still being worked on (an extra click)."""
    if not text.strip() or screen(graph, case_id) != ASKING:
        return
    with running(case_id) as claimed:
        if claimed:
            graph.invoke({"messages": [{"role": "user", "content": clean_message(text)}]}, _config(case_id))


def screen(graph, case_id: str) -> str:
    """Which screen the page should show for this case."""
    snapshot = graph.get_state(_config(case_id))
    values = snapshot.values
    if snapshot.interrupts:
        return WAITING_FOR_VOLUNTEER
    if values.get("status") in ("halted_by_human", "halted_by_error"):  # the taxpayer text is neutral for both
        return STOPPED
    if snapshot.next:  # a step is running, or raised an error part-way (e.g. reading the W-2); nothing is lost
        return READING if is_running(case_id) else READING_FAILED
    if values.get("done") or values.get("intake_complete"):
        return FINISHED
    return ASKING


def draft_form_html(graph, case_id: str) -> str | None:
    """The draft 1040-SR page for a case (PRV-3), or None when nothing has been computed yet.
    Every amount expands to its formula, inputs, source and tool; nothing has been filed."""
    values = graph.get_state(_config(case_id)).values
    if not values.get("computed"):
        return None
    try:
        return render_draft_html(
            values["computed"], values.get("facts"), values.get("eligibility"),
            review=values.get("review"), review_history=values.get("review_history"),
            decisions=values.get("human_decisions"), case_id=case_id,
            extracted=values.get("extracted"))  # so a form that was not read shows "Income is missing"
    except ValueError:  # a line without provenance is never shown
        return None


def transcript(graph, case_id: str) -> list[dict]:
    """The conversation so far, as [{"role": "user"|"assistant", "content": ...}]."""
    return list(graph.get_state(_config(case_id)).values.get("messages", []))


def welcome_back(graph, case_id: str) -> str:
    return intake_agent.welcome_back(graph.get_state(_config(case_id)).values.get("facts", {}))


def answers(graph, case_id: str) -> list[dict]:
    """The "Your answers so far" list: [{"key", "question", "answer"}]."""
    return intake_agent.answers_so_far(graph.get_state(_config(case_id)).values.get("facts", {}))


# Month choices are just the names ("March"), so a choice never looks like a date such as
# "2 - February". Typing "mar" finds March.
MONTH_OPTIONS = list(calendar.month_name)[1:]


def asking_for_a_date(graph, case_id: str) -> bool:
    """Show the Month / Day / Year boxes instead of only the free-text box."""
    facts = graph.get_state(_config(case_id)).values.get("facts", {})
    return screen(graph, case_id) == ASKING and intake_agent.asking_for_a_date(facts)


def date_answer(month_option: str | None, day: int | None, year: int | None) -> str | None:
    """("March", 4, 1950) -> "March 4, 1950", or None if a box is empty. Intake still reads
    the date back to the person before saving it."""
    if not month_option or not day or not year:
        return None
    return f"{month_option} {int(day)}, {int(year)}"


# The typed-date box asks for MM-DD-YYYY, so month-first is safe to assume there.
_TYPED_DATE = re.compile(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})$|^(\d{2})(\d{2})(\d{4})$")


def typed_date(text: str) -> str:
    """"03-04-1950", "03/04/1950" or "03041950" -> "March 4, 1950", because the label asks for
    MM-DD-YYYY. Anything else is sent as typed; Intake reads it back to the person either way."""
    match = _TYPED_DATE.match((text or "").replace(" ", ""))
    if not match:
        return text
    month, day, year = (int(part) for part in match.groups() if part)
    if not 1 <= month <= 12:
        return text  # e.g. "13-04-1950" is day-first: let Intake read it and check with the person
    return date_answer(MONTH_OPTIONS[month - 1], day, year)


PARTS = [title for title, _ in intake_agent.PARTS]


def _facts(graph, case_id: str) -> dict:
    return graph.get_state(_config(case_id)).values.get("facts", {})


def question_label(graph, case_id: str) -> dict | None:
    """{"part", "part_title", "number"}, e.g. 2, "Age and eyesight", "2.3"."""
    return intake_agent.question_label(_facts(graph, case_id))


def overview(graph, case_id: str) -> list[dict]:
    """The six parts with their status in words, for the progress list."""
    return intake_agent.parts_overview(_facts(graph, case_id))


def date_problem(month_option: str | None, day: int | None, year: int | None) -> str | None:
    """Checked before sending, e.g. "April has only 30 days. Please check the day." """
    if not month_option or not day or not year:
        return None
    return intake_agent.day_problem(MONTH_OPTIONS.index(month_option) + 1, int(day), int(year))


def change(graph, case_id: str, question_text: str) -> None:
    """A "Change" button: Intake jumps straight back to that question."""
    send(graph, case_id, f"{intake_agent.CHANGE_PREFIX}{question_text}")


# ---- W-2 photo ---------------------------------------------------------------------------------

W2_CONFIRM_FIRST = "Please tick the box to confirm this is not a real tax form."
W2_NOT_ADDED = ("Sorry, we couldn't add that photo. Please check it is a JPG or PNG picture of the W-2 "
                "and try again, or carry on and a volunteer will help.")


def show_w2_upload(graph, case_id: str) -> bool:
    """Offer the W-2 upload: the taxpayer said "yes" to the W-2 question and the questions are
    not over (JiWon's service refuses a photo after that)."""
    has_w2 = _facts(graph, case_id).get("has_w2") or {}
    return screen(graph, case_id) == ASKING and has_w2.get("value") == "yes"


def waiting_for_w2(graph, case_id: str, later: bool = False) -> bool:
    """Right after "yes" to the W-2 question, the next screen asks only for the photo: the other
    questions wait until a photo is added or the taxpayer presses "I don't have it now" (`later`).
    Agreed with Francesca and JiWon: holding here, not at the last answer, because which question
    is last is not known in advance (skipped questions come back at the end)."""
    return show_w2_upload(graph, case_id) and not later and w2_photos(graph, case_id) == 0


def w2_photos(graph, case_id: str) -> int:
    """How many W-2 photos this case has."""
    documents = graph.get_state(_config(case_id)).values.get("documents") or []
    return sum(1 for d in documents if d.get("kind") == "W-2" and d.get("image_ref"))


def add_w2(service, case_id: str, data: bytes | None, confirmed: bool) -> str | None:
    """Add a W-2 photo to the case. Returns a message for the taxpayer if it was not added, or None.
    The photo is read when the questions end, not now."""
    if not confirmed:
        return W2_CONFIRM_FIRST
    if not data:
        return W2_NOT_ADDED
    try:
        service.submit(case_id, data, synthetic_confirmed=True)
    except (SafeInputError, OSError, ValueError):
        return W2_NOT_ADDED
    return None


def note_reading_failure(problem: Exception) -> None:
    """The taxpayer sees the friendly "Try again" screen; the cause goes to the app's log (type and a
    short message only: no traceback with local values, and a key is never in an error message)."""
    logging.getLogger("silverfile.chat").warning("W-2 reading failed: %s: %s", type(problem).__name__,
                                                 " ".join(str(problem).split())[:300])


def try_again(graph, case_id: str) -> None:
    """Carry on from the step that failed (e.g. reading the W-2 photo); answers are kept."""
    with running(case_id) as claimed:  # an extra click while it is already running is ignored
        if claimed:
            graph.invoke(None, _config(case_id))
