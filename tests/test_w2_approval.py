"""A volunteer checks a W-2 reading in the dashboard (P2 of the team's to-do list): the photo beside the
amounts read, then accept (optionally correcting a box) or reject, through JiWon's shared service.
Offline: a fake photo reader stands in for the AI."""
import sys
from pathlib import Path

import pytest
import streamlit as st
from langgraph.checkpoint.memory import InMemorySaver

from src.ui import chat_session as chat
from src.ui import dashboard_data as dash
from tests.test_intake_agent import FULL_ANSWERS

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests_p3"))
from p3_helpers import FakeReader  # noqa: E402  (JiWon's offline stand-in for the AI: box 1 30,000, box 2 2,000)

W2_PHOTO = (ROOT / "data" / "fixtures" / "w2_01.jpg").read_bytes()  # one of the project's sample W-2s
CASE = "SF-900-456"


def waiting_for_the_w2_check(service):
    """A taxpayer adds a W-2 photo and finishes the questions; the reading waits for a volunteer."""
    graph = service.graph
    chat.start(graph, CASE)
    answers = list(FULL_ANSWERS)
    while not chat.show_w2_upload(graph, CASE):
        chat.send(graph, CASE, answers.pop(0))
    assert chat.add_w2(service, CASE, W2_PHOTO, confirmed=True) is None
    for answer in answers:
        chat.send(graph, CASE, answer)
    return service


@pytest.fixture
def service(tmp_path, monkeypatch):
    monkeypatch.setattr(chat, "RUNTIME", str(tmp_path / "runtime"))
    monkeypatch.setattr(dash, "TRACE_DIR", str(tmp_path))
    return waiting_for_the_w2_check(
        chat.make_app_service(trace_dir=tmp_path, reader=FakeReader(), saved_sessions=InMemorySaver()))


def computed(service):
    return service.graph.get_state({"configurable": {"thread_id": CASE}}).values.get("computed", {})


def test_the_volunteer_sees_the_photo_and_each_amount_read(service):
    reading = dash.w2_reading(service, CASE)
    assert reading["photo"][:8] == b"\x89PNG\r\n\x1a\n"  # the photo the taxpayer added
    assert [(b["box"], b["amount"], b["seen"]) for b in reading["boxes"]] == [
        ("1", "30000.00", "30,000.00"), ("2", "2000.00", "2,000.00")]
    assert reading["boxes"][0]["label"] == "Wages, tips, other compensation"
    assert reading["tax_year"] == 2025 and reading["needs_amount"] == []


def test_accepting_finishes_the_draft_with_the_w2_amounts(service):
    assert dash.decide_w2(service, CASE, True, "Amounts match the photo.", "Pat Volunteer", checked_photo=True) is None
    assert chat.screen(service.graph, CASE) == chat.FINISHED
    assert (computed(service)["line_1z"]["value"], computed(service)["line_25a"]["value"]) == (30000.0, 2000.0)
    decided = next(r for r in dash.history(CASE) if r["what"] == "Volunteer decided")
    assert decided["who"] == "volunteer:Pat Volunteer"


def test_a_corrected_amount_is_used_instead_of_the_one_read(service):
    assert dash.decide_w2(service, CASE, True, "Box 1 is 31,000 on the photo.", "Pat Volunteer",
                          checked_photo=True, corrections={"1": "31000.00", "2": " "}) is None
    assert computed(service)["line_1z"]["value"] == 31000.0
    assert computed(service)["line_25a"]["value"] == 2000.0  # an empty box keeps the amount read


def test_accepting_needs_the_photo_checked(service):
    error = dash.decide_w2(service, CASE, True, "Looks fine.", "Pat Volunteer", checked_photo=False)
    assert "Confirm visually" in error
    assert dash.w2_reading(service, CASE) is not None  # still waiting


@pytest.mark.parametrize("note, name, words", [("Fine.", "  ", "your name"), (" ", "Pat Volunteer", "short note")])
def test_a_name_and_a_note_are_required(service, note, name, words):
    assert words in dash.decide_w2(service, CASE, True, note, name, checked_photo=True)
    assert dash.w2_reading(service, CASE) is not None


def test_an_amount_that_is_not_money_is_refused(service):
    assert dash.decide_w2(service, CASE, True, "Typed box 1.", "Pat Volunteer", checked_photo=True,
                          corrections={"1": "about thirty thousand"})
    assert dash.w2_reading(service, CASE) is not None


def test_rejecting_stops_the_case(service):
    assert dash.decide_w2(service, CASE, False, "The photo is blurred.", "Pat Volunteer") is None
    assert chat.screen(service.graph, CASE) == chat.STOPPED


def test_a_second_volunteer_is_told_it_was_already_decided(service):
    assert dash.decide_w2(service, CASE, True, "Matches.", "Pat Volunteer", checked_photo=True) is None
    assert dash.decide_w2(service, CASE, False, "Blurred.", "Sam Volunteer") == dash.NO_LONGER_WAITING


def test_no_reading_when_the_case_is_not_waiting_for_one(tmp_path, monkeypatch):
    monkeypatch.setattr(chat, "RUNTIME", str(tmp_path / "runtime"))
    service = chat.make_app_service(trace_dir=tmp_path, reader=FakeReader(), saved_sessions=InMemorySaver())
    chat.start(service.graph, CASE)
    assert dash.w2_reading(service, CASE) is None


# ---- the page ----------------------------------------------------------------------------------


def test_page_shows_the_photo_the_amounts_and_the_choices(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setattr(chat, "SAVED_SESSIONS_FILE", str(tmp_path / "sessions.sqlite"))
    monkeypatch.setattr(chat, "RUNTIME", str(tmp_path / "runtime"))
    monkeypatch.setattr(chat, "ENV_FILE", str(tmp_path / "no.env"))
    monkeypatch.setattr(dash, "TRACE_DIR", str(tmp_path))
    st.cache_resource.clear()
    waiting_for_the_w2_check(chat.make_app_service(trace_dir=tmp_path, reader=FakeReader()))
    page = AppTest.from_file(str(ROOT / "src" / "ui" / "volunteer_dashboard.py"), default_timeout=30)
    page.session_state.open_case = CASE
    page.run()
    assert not page.exception
    assert page.get("image")  # the W-2 photo
    assert [c.label for c in page.checkbox] == ["I compared the amounts with the photo, and this is a W-2."]
    assert len(page.radio[0].options) == 2
    assert any("Box 1 (Wages" in t.label for t in page.text_input)
