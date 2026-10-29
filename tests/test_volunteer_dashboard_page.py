"""Page tests for the volunteer dashboard (src/ui/volunteer_dashboard.py), driven like a volunteer."""
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from src.ui import chat_session as chat
from src.ui import dashboard_data as dash
from tests.test_intake_agent import NAME

PAGE = str(Path(__file__).resolve().parents[1] / "src" / "ui" / "volunteer_dashboard.py")


@pytest.fixture
def saved(tmp_path, monkeypatch):
    """A temporary saved-sessions file and audit log, shared by the test and the page."""
    monkeypatch.setattr(chat, "SAVED_SESSIONS_FILE", str(tmp_path / "sessions.sqlite"))
    monkeypatch.setattr(dash, "TRACE_DIR", str(tmp_path))
    st.cache_resource.clear()
    return dash.open_graph()


def taxpayer(graph, case_id, *answers):
    chat.start(graph, case_id)
    for answer in [NAME, *answers]:
        chat.send(graph, case_id, answer)


def open_page():
    return AppTest.from_file(PAGE, default_timeout=30).run()


def test_empty_dashboard_says_so(saved):
    page = open_page()
    assert not page.exception
    assert any("No cases yet" in i.value for i in page.info)


def test_list_shows_counts_and_the_alarm_first(saved):
    taxpayer(saved, "SF-200-001", "no")
    taxpayer(saved, "SF-200-002", "Should I file jointly?")
    page = open_page()
    assert not page.exception
    assert [m.value for m in page.metric][:2] == ["1", "1"]  # 1 needs a volunteer, 1 answering
    rows = [m.value for m in page.markdown if "<b>SF-200-" in m.value]
    assert "SF-200-002" in rows[0]  # the case needing a volunteer is listed first


def test_a_volunteer_resolves_an_alarm_and_the_taxpayer_carries_on(saved):
    taxpayer(saved, "SF-200-003", "Should I file jointly?")
    page = open_page()
    page.sidebar.text_input[0].input("Pat Volunteer")
    page.button(key="open-SF-200-003").click().run()
    assert any("Needs your decision" in s.value for s in page.subheader)
    page.radio[0].set_value("continue")
    page.text_area[0].input("Noted the question for the preparer.")
    next(b for b in page.button if b.label == "Save decision").click().run()
    assert not page.exception
    assert any("Decision saved" in s.value for s in page.success)
    assert chat.screen(saved, "SF-200-003") == chat.ASKING
    assert any(r["who"] == "volunteer:Pat Volunteer" and r["what"] == "Volunteer decided"
               for r in dash.history("SF-200-003"))


def test_pressure_shows_only_stop_and_why(saved):
    taxpayer(saved, "SF-200-004", "He keeps my refund")
    page = open_page()
    page.button(key="open-SF-200-004").click().run()
    assert page.radio[0].options == ["Stop the case"]
    assert any(dash.STOP_ONLY_WHY in i.value for i in page.info)
    assert any('Taxpayer said: "He keeps my refund"' in m.value for m in page.markdown)


def test_saving_without_a_name_is_refused(saved):
    taxpayer(saved, "SF-200-005", "Should I file jointly?")
    page = open_page()
    page.button(key="open-SF-200-005").click().run()
    page.radio[0].set_value("continue")
    page.text_area[0].input("Noted.")
    next(b for b in page.button if b.label == "Save decision").click().run()
    assert any("your name" in e.value for e in page.error)
    assert chat.screen(saved, "SF-200-005") == chat.WAITING_FOR_VOLUNTEER
