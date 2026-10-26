"""Tests for the taxpayer chat page (card INT-6): the chat logic and a page smoke test."""
import re

import pytest
from langgraph.types import Command

from src.agents import intake_agent as ia
from src.ui import chat_session as chat
from tests.test_intake_agent import FULL_ANSWERS, NAME


@pytest.fixture
def graph(tmp_path):
    return chat.make_graph(trace_dir=tmp_path)


def start_named(graph, case_id):
    """Start a session and answer the first question ("What is your full name?")."""
    chat.start(graph, case_id)
    chat.send(graph, case_id, NAME)


def test_new_case_id_is_short_and_readable():
    case_id = chat.new_case_id()
    assert re.fullmatch(r"SF-\d{3}-\d{3}", case_id)


@pytest.mark.parametrize("typed, expected", [
    ("SF-482-735", "SF-482-735"), ("sf 482 735", "SF-482-735"), ("SF482735", "SF-482-735"),
    ("482-735", "SF-482-735"), ("SF-482-73", None), ("AB-482-735", None), ("", None),
])
def test_clean_case_id(typed, expected):
    assert chat.clean_case_id(typed) == expected


def test_start_asks_the_first_question(graph):
    chat.start(graph, "SF-000-001")
    assert chat.exists(graph, "SF-000-001")
    assert not chat.exists(graph, "SF-999-999")
    assert chat.screen(graph, "SF-000-001") == chat.ASKING
    assert chat.transcript(graph, "SF-000-001")[-1]["content"].endswith("What is your full name?")
    chat.send(graph, "SF-000-001", NAME)
    assert chat.transcript(graph, "SF-000-001")[-1]["content"].endswith("were you married?")


def test_answers_move_the_conversation_on(graph):
    start_named(graph, "SF-000-002")
    chat.send(graph, "SF-000-002", "no")
    assert "single, widowed" in chat.transcript(graph, "SF-000-002")[-1]["content"]


def test_real_ssn_never_enters_the_graph(graph):
    start_named(graph, "SF-000-003")
    chat.send(graph, "SF-000-003", "no, my number is 123-45-6789")
    state = graph.get_state({"configurable": {"thread_id": "SF-000-003"}}).values
    assert "123-45-6789" not in str(state)
    assert ia.SSN_REMOVED in chat.transcript(graph, "SF-000-003")[-2]["content"]


def test_practice_ssn_is_kept_for_the_dependent_question():
    assert chat.clean_message("900-11-2222") == "900-11-2222"
    assert chat.clean_message("123-45-6789") == ia.SSN_REMOVED


def test_volunteer_pause_blocks_messages_until_resolved(graph):
    case_id = "SF-000-004"
    chat.start(graph, case_id)
    chat.send(graph, case_id, "Should I file jointly?")
    assert chat.screen(graph, case_id) == chat.WAITING_FOR_VOLUNTEER
    before = len(chat.transcript(graph, case_id))
    chat.send(graph, case_id, "hello?")  # ignored while waiting
    assert len(chat.transcript(graph, case_id)) == before
    graph.invoke(Command(resume={"decision": "continue", "note": "noted"}),
                 {"configurable": {"thread_id": case_id}})
    assert chat.screen(graph, case_id) == chat.ASKING


def test_volunteer_stop_shows_stopped(graph):
    case_id = "SF-000-005"
    chat.start(graph, case_id)
    chat.send(graph, case_id, "My son is pressuring me to sign")
    graph.invoke(Command(resume={"decision": "stop", "note": "call client"}),
                 {"configurable": {"thread_id": case_id}})
    assert chat.screen(graph, case_id) == chat.STOPPED


def test_full_session_finishes(graph):
    case_id = "SF-000-006"
    chat.start(graph, case_id)
    for answer in FULL_ANSWERS:
        chat.send(graph, case_id, answer)
    assert chat.screen(graph, case_id) == chat.FINISHED


def test_continuing_a_session_gives_a_summary(graph):
    case_id = "SF-000-007"
    chat.start(graph, case_id)
    assert chat.welcome_back(graph, case_id) == "Welcome back. We haven't covered any questions yet."
    for answer in [NAME, "no", "single", "March 4, 1950", "yes"]:
        chat.send(graph, case_id, answer)
    assert chat.welcome_back(graph, case_id) == (
        "Welcome back. So far we've covered: your name, whether you were married, your household "
        "and your date of birth."
    )


def test_answers_list_and_change(graph):
    case_id = "SF-000-008"
    start_named(graph, case_id)
    for answer in ["no", "single", "dec, 4,1950", "yes"]:
        chat.send(graph, case_id, answer)
    rows = chat.answers(graph, case_id)
    assert [r["answer"] for r in rows] == [NAME, "no", "single", "December 4, 1950"]
    chat.change(graph, case_id, rows[1]["question"])
    assert chat.transcript(graph, case_id)[-1]["content"].startswith("Sure, let's change that. Earlier you said: no.")


def test_date_answer_from_the_three_boxes():
    assert chat.MONTH_OPTIONS[2] == "3 - March"
    assert chat.date_answer("3 - March", 4, 1950) == "March 4, 1950"
    assert chat.date_answer("12 - December", 4.0, 1950.0) == "December 4, 1950"
    assert chat.date_answer(None, 4, 1950) is None
    assert chat.date_answer("3 - March", None, 1950) is None


def test_date_boxes_only_while_asking_for_a_date(graph):
    case_id = "SF-000-009"
    start_named(graph, case_id)
    assert not chat.asking_for_a_date(graph, case_id)
    chat.send(graph, case_id, "no")
    chat.send(graph, case_id, "single")
    assert chat.asking_for_a_date(graph, case_id)
    chat.send(graph, case_id, chat.date_answer("3 - March", 4, 1950))
    assert not chat.asking_for_a_date(graph, case_id)  # now reading it back to check
    assert chat.transcript(graph, case_id)[-1]["content"].endswith("March 4, 1950. Is that right?")


def test_question_numbers_have_no_gaps_and_match_the_answers_list(graph):
    case_id = "SF-000-010"
    chat.start(graph, case_id)
    assert chat.question_number(graph, case_id) == 1  # the name
    chat.send(graph, case_id, NAME)
    chat.send(graph, case_id, "no")      # Q1; Q2 is skipped for someone not married
    assert chat.question_number(graph, case_id) == 3  # Q3 is shown as "Question 3"
    chat.send(graph, case_id, "single")
    chat.send(graph, case_id, "March 4, 1950")
    assert chat.question_number(graph, case_id) == 4  # the read-back keeps the same number
    chat.send(graph, case_id, "yes")
    assert chat.question_number(graph, case_id) == 5
    chat.change(graph, case_id, chat.answers(graph, case_id)[2]["question"])  # "Change answer 3"
    assert chat.question_number(graph, case_id) == 3


def test_page_shows_answers_and_change_buttons():
    from streamlit.testing.v1 import AppTest

    page = AppTest.from_file("src/ui/taxpayer_chat.py", default_timeout=30).run()
    page.button[0].click().run()
    for answer in [NAME, "no"]:
        page.text_input[0].input(answer)
        next(b for b in page.button if b.label == "Send my answer").click().run()
    assert not page.exception
    assert any(b.label == "Change answer 2" for b in page.button)
    assert any(h.value == "Question 3" for h in page.header)


def test_page_date_boxes_send_a_date():
    from streamlit.testing.v1 import AppTest

    page = AppTest.from_file("src/ui/taxpayer_chat.py", default_timeout=30).run()
    page.button[0].click().run()
    for answer in [NAME, "no", "single"]:
        page.text_input[0].input(answer)
        next(b for b in page.button if b.label == "Send my answer").click().run()
    assert page.selectbox[0].options[2] == "3 - March"
    page.selectbox[0].select("3 - March")
    page.number_input[0].set_value(4)
    page.number_input[1].set_value(1950)
    next(b for b in page.button if b.label == "Send this date").click().run()
    assert not page.exception
    assert any("March 4, 1950. Is that right?" in m.value for m in page.markdown)


def test_page_loads_and_starts_a_session():
    from streamlit.testing.v1 import AppTest

    page = AppTest.from_file("src/ui/taxpayer_chat.py", default_timeout=30).run()
    assert not page.exception
    assert page.button[0].label == "Start a new session"
    page.button[0].click().run()
    assert not page.exception
    assert re.fullmatch(r"SF-\d{3}-\d{3}", page.session_state.case_id)
    assert any("What is your full name?" in m.value for m in page.markdown)
