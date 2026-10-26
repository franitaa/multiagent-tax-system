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
    because Intake needs them for dependents (agreed with Sahana's 900-999 rule).
  - Tells the page what to show: waiting for an answer, waiting for a volunteer (no new
    messages accepted, as the contract asks), finished, or stopped by a volunteer.
  - Gives a "welcome back, so far we've covered..." summary when a session is continued.
  - Lists "Your answers so far"; each has a Change button that jumps straight to that question.
  - The conversation is split into 6 parts like an application form: `overview()` gives each
    part's status in words, and `question_label()` gives "Part 2 of 6, Question 2.3".
  - For date questions, the page shows Month / Day / Year boxes (`MONTH_OPTIONS`,
    `date_answer`), so day-first vs month-first can never be mixed up.

What is still missing:
  - Permanent storage. `make_graph()` uses LangGraph's in-memory store by default, so
    sessions last only while the app is running. Shruti's checkpointer (MEM-1) plugs in
    through `make_graph(checkpointer=...)`; nothing else needs to change.
  - Uses the real Intake directly (`intake_agent.run`); the other agents are still stubs.
"""
import calendar
import re
import secrets

from src.agents import intake_agent
from src.graph import build_graph

# What the page should show
ASKING = "asking"  # a question is waiting for the taxpayer's answer
WAITING_FOR_VOLUNTEER = "waiting_for_volunteer"
FINISHED = "finished"
STOPPED = "stopped"

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


def make_graph(checkpointer=None, trace_dir="traces"):
    """The SilverFile graph with the real Intake. Pass Shruti's checkpointer when ready."""
    return build_graph(checkpointer, trace_dir=trace_dir, agents={"intake": intake_agent.run})


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


def send(graph, case_id: str, text: str) -> None:
    """Send one taxpayer message. Ignored while a volunteer is needed or the case is over."""
    if not text.strip() or screen(graph, case_id) != ASKING:
        return
    graph.invoke({"messages": [{"role": "user", "content": clean_message(text)}]}, _config(case_id))


def screen(graph, case_id: str) -> str:
    """Which screen the page should show for this case."""
    snapshot = graph.get_state(_config(case_id))
    values = snapshot.values
    if snapshot.interrupts:
        return WAITING_FOR_VOLUNTEER
    if values.get("status") == "halted_by_human":
        return STOPPED
    if values.get("done") or values.get("intake_complete"):
        return FINISHED
    return ASKING


def transcript(graph, case_id: str) -> list[dict]:
    """The conversation so far, as [{"role": "user"|"assistant", "content": ...}]."""
    return list(graph.get_state(_config(case_id)).values.get("messages", []))


def welcome_back(graph, case_id: str) -> str:
    return intake_agent.welcome_back(graph.get_state(_config(case_id)).values.get("facts", {}))


def answers(graph, case_id: str) -> list[dict]:
    """The "Your answers so far" list: [{"key", "question", "answer"}]."""
    return intake_agent.answers_so_far(graph.get_state(_config(case_id)).values.get("facts", {}))


# Month choices show the number and the name, so typing "3" or "mar" both find "3 - March".
MONTH_OPTIONS = [f"{number} - {calendar.month_name[number]}" for number in range(1, 13)]


def asking_for_a_date(graph, case_id: str) -> bool:
    """Show the Month / Day / Year boxes instead of only the free-text box."""
    facts = graph.get_state(_config(case_id)).values.get("facts", {})
    return screen(graph, case_id) == ASKING and intake_agent.asking_for_a_date(facts)


def date_answer(month_option: str | None, day: int | None, year: int | None) -> str | None:
    """("3 - March", 4, 1950) -> "March 4, 1950", or None if a box is empty. Intake still reads
    the date back to the person before saving it."""
    if not month_option or not day or not year:
        return None
    return f"{month_option.split(' - ')[1]} {int(day)}, {int(year)}"


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
    return intake_agent.day_problem(int(month_option.split(" - ")[0]), int(day), int(year))


def change(graph, case_id: str, question_text: str) -> None:
    """A "Change" button: Intake jumps straight back to that question."""
    send(graph, case_id, f"{intake_agent.CHANGE_PREFIX}{question_text}")
