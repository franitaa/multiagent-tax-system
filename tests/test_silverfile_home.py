"""The start page opens both the taxpayer chat and the volunteer dashboard in one app."""
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from src.ui import chat_session as chat
from src.ui import dashboard_data as dash
from tests.test_intake_agent import NAME

HOME = str(Path(__file__).resolve().parents[1] / "src" / "ui" / "silverfile_home.py")


@pytest.fixture(autouse=True)
def saved(tmp_path, monkeypatch):
    monkeypatch.setattr(chat, "SAVED_SESSIONS_FILE", str(tmp_path / "sessions.sqlite"))
    monkeypatch.setattr(dash, "TRACE_DIR", str(tmp_path))
    st.cache_resource.clear()


def test_start_page_offers_both_choices():
    page = AppTest.from_file(HOME, default_timeout=30).run()
    assert not page.exception
    headings = [m.value for m in page.markdown if '<h2 class="card-title">' in m.value]
    assert ["I'm a taxpayer" in headings[0], "I'm a Kushim volunteer" in headings[1]] == [True, True]
    assert [link.label for link in page.get("page_link")] == ["Start or continue my questions",
                                                              "Open the volunteer dashboard"]


def test_taxpayer_and_volunteer_pages_share_the_same_cases():
    page = AppTest.from_file(HOME, default_timeout=30).run()
    page.switch_page(str(Path(HOME).parent / "taxpayer_chat.py")).run()
    assert not page.exception
    page.button[0].click().run()  # Start a new session
    case_id = page.session_state.case_id
    page.text_input[0].input(NAME)
    next(b for b in page.button if b.label == "Send my answer").click().run()

    page.switch_page(str(Path(HOME).parent / "volunteer_dashboard.py")).run()
    assert not page.exception
    assert any(f"<b>{case_id}</b>" in m.value for m in page.markdown)  # the chat's case is listed
    assert page.session_state.case_id == case_id  # the dashboard did not change the chat's session


def test_telemetry_is_a_hidden_page_not_linked_from_the_start_page():
    page = AppTest.from_file(HOME, default_timeout=30).run()
    assert [link.label for link in page.get("page_link")] == ["Start or continue my questions",
                                                              "Open the volunteer dashboard"]
    page.switch_page(str(Path(HOME).parent / "telemetry_dashboard.py")).run()
    assert not page.exception
    assert any("SilverFile telemetry" in t.value for t in page.title)
