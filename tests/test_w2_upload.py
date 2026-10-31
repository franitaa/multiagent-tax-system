"""The W-2 photo step in the taxpayer chat (P1 of the team's to-do list), with JiWon's shared service.
Offline: a fake photo reader stands in for the AI, and no API key is read."""
import sys
from pathlib import Path

import pytest
import streamlit as st
from langgraph.checkpoint.memory import InMemorySaver

from silverfile_extraction.privacy import SafeInputError
from src import state as S
from src.ui import chat_session as chat
from tests.test_intake_agent import FULL_ANSWERS

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests_p3"))
from p3_helpers import FakeReader  # noqa: E402  (JiWon's offline stand-in for the AI)

W2_PHOTO = (ROOT / "data" / "fixtures" / "w2_01.jpg").read_bytes()  # one of the project's sample W-2s
CASE = "SF-900-123"


class BrokenReader:
    """Reading the photo fails, as with no internet or a rejected key."""
    def read(self, png, context):
        raise SafeInputError("Could not connect. Check your connection and retry.")


@pytest.fixture
def service(tmp_path, monkeypatch):
    monkeypatch.setattr(chat, "RUNTIME", str(tmp_path / "runtime"))
    return chat.make_app_service(trace_dir=tmp_path, reader=FakeReader(), saved_sessions=InMemorySaver())


def answer_until_the_w2_question_is_answered(graph):
    """Start the case and answer until the taxpayer has said "yes" to the W-2 question.
    Returns the answers still to give."""
    chat.start(graph, CASE)
    answers = list(FULL_ANSWERS)
    while not chat.show_w2_upload(graph, CASE):
        chat.send(graph, CASE, answers.pop(0))
    return answers


def test_the_upload_is_offered_only_after_yes_to_the_w2_question(service):
    graph = service.graph
    chat.start(graph, CASE)
    for answer in FULL_ANSWERS:
        facts = graph.get_state({"configurable": {"thread_id": CASE}}).values.get("facts", {})
        assert chat.show_w2_upload(graph, CASE) == ("has_w2" in facts)  # never before the answer
        if "has_w2" in facts:
            break
        chat.send(graph, CASE, answer)
    assert chat.show_w2_upload(graph, CASE)


def test_the_photo_needs_the_made_up_confirmation(service):
    answer_until_the_w2_question_is_answered(service.graph)
    assert chat.add_w2(service, CASE, W2_PHOTO, confirmed=False) == chat.W2_CONFIRM_FIRST
    assert chat.w2_photos(service.graph, CASE) == 0


def test_something_that_is_not_a_picture_is_refused_kindly(service):
    answer_until_the_w2_question_is_answered(service.graph)
    assert chat.add_w2(service, CASE, b"not a picture", confirmed=True) == chat.W2_NOT_ADDED
    assert chat.add_w2(service, CASE, None, confirmed=True) == chat.W2_NOT_ADDED
    assert chat.w2_photos(service.graph, CASE) == 0


def test_a_w2_photo_is_read_when_the_questions_end_and_a_volunteer_checks_it(service):
    graph = service.graph
    remaining = answer_until_the_w2_question_is_answered(graph)
    assert chat.add_w2(service, CASE, W2_PHOTO, confirmed=True) is None
    assert chat.w2_photos(graph, CASE) == 1
    assert service.reader.calls == []  # not read yet: only when the questions end
    for answer in remaining:
        chat.send(graph, CASE, answer)
    assert len(service.reader.calls) == 1
    assert chat.screen(graph, CASE) == chat.WAITING_FOR_VOLUNTEER
    waiting = graph.get_state({"configurable": {"thread_id": CASE}}).interrupts[0].value
    assert waiting["condition"] == S.EXTRACTION_REVIEW  # a volunteer compares the amounts with the photo
    facts = graph.get_state({"configurable": {"thread_id": CASE}}).values["facts"]
    assert facts["has_w2"]["value"] == "yes"  # adding the photo changed no answer


def test_the_same_photo_twice_counts_once(service):
    answer_until_the_w2_question_is_answered(service.graph)
    assert chat.add_w2(service, CASE, W2_PHOTO, confirmed=True) is None
    assert chat.add_w2(service, CASE, W2_PHOTO, confirmed=True) is None
    assert chat.w2_photos(service.graph, CASE) == 1


def test_no_upload_after_the_questions_end(service):
    graph = service.graph
    chat.start(graph, CASE)
    for answer in FULL_ANSWERS:
        chat.send(graph, CASE, answer)
    assert not chat.show_w2_upload(graph, CASE)  # the case now waits for a volunteer (INCOME_NOT_READ)


def test_if_reading_fails_nothing_is_lost_and_try_again_carries_on(tmp_path, monkeypatch):
    monkeypatch.setattr(chat, "RUNTIME", str(tmp_path / "runtime"))
    service = chat.make_app_service(trace_dir=tmp_path, reader=BrokenReader(), saved_sessions=InMemorySaver())
    graph = service.graph
    remaining = answer_until_the_w2_question_is_answered(graph)
    assert chat.add_w2(service, CASE, W2_PHOTO, confirmed=True) is None
    with pytest.raises(SafeInputError):
        for answer in remaining:
            chat.send(graph, CASE, answer)
    assert chat.screen(graph, CASE) == chat.READING_FAILED
    answers_before = chat.answers(graph, CASE)
    service.reader = FakeReader()  # e.g. the internet is back
    chat.try_again(graph, CASE)
    assert chat.screen(graph, CASE) == chat.WAITING_FOR_VOLUNTEER
    assert chat.answers(graph, CASE) == answers_before


@pytest.mark.parametrize("env, provider", [
    ("OPENAI_API_KEY=sk-test-openai\n", "openai"),
    ("ANTHROPIC_API_KEY=sk-ant-test\n", "anthropic"),
    ("OPENAI_API_KEY=sk-test-openai\nANTHROPIC_API_KEY=sk-ant-test\n", "openai"),
])
def test_the_photo_reader_uses_the_key_in_the_env_file(tmp_path, env, provider):
    env_file = tmp_path / ".env"
    env_file.write_text(env, encoding="utf-8")
    assert chat.photo_reader(str(env_file)).provider == provider


@pytest.mark.parametrize("env", ["", "OPENAI_API_KEY=\n", "OPENAI_API_KEY=sk-ant-a-claude-key\n"])
def test_no_usable_key_means_no_photo_reader(tmp_path, env):
    env_file = tmp_path / ".env"
    env_file.write_text(env, encoding="utf-8")
    assert chat.photo_reader(str(env_file)) is None
    assert chat.photo_reader(str(tmp_path / "missing.env")) is None


# ---- the page ----------------------------------------------------------------------------------


@pytest.fixture
def page_case(tmp_path, monkeypatch):
    """A case on the page's saved-sessions file, answered up to "yes" to the W-2 question."""
    monkeypatch.setattr(chat, "SAVED_SESSIONS_FILE", str(tmp_path / "sessions.sqlite"))
    monkeypatch.setattr(chat, "RUNTIME", str(tmp_path / "runtime"))
    monkeypatch.setattr("src.ui.dashboard_data.TRACE_DIR", str(tmp_path))
    st.cache_resource.clear()

    def make(env_text, with_photo=False):
        env_file = tmp_path / ".env"
        env_file.write_text(env_text, encoding="utf-8")
        monkeypatch.setattr(chat, "ENV_FILE", str(env_file))
        service = chat.make_app_service(trace_dir=tmp_path, reader=FakeReader())
        answer_until_the_w2_question_is_answered(service.graph)
        if with_photo:
            assert chat.add_w2(service, CASE, W2_PHOTO, confirmed=True) is None
        from streamlit.testing.v1 import AppTest
        page = AppTest.from_file(str(ROOT / "src" / "ui" / "taxpayer_chat.py"), default_timeout=30)
        page.session_state.case_id = CASE
        return page.run()
    return make


def answer_box(page):
    return [t for t in page.text_input if t.label == "Type your answer here"]


def test_page_after_yes_asks_only_for_the_w2_photo(page_case):
    page = page_case("OPENAI_API_KEY=sk-test-openai\n")
    assert not page.exception
    assert any("Your W-2 form" in m.value for m in page.markdown)
    assert [c.label for c in page.checkbox] == ["I confirm this is not a real tax form."]
    assert any("Please never upload a real tax form" in m.value for m in page.markdown)
    assert not answer_box(page)  # the next question waits for the photo or "I don't have it now"
    assert {"Add my W-2", "I don't have it now"} <= {b.label for b in page.button}


def test_page_i_dont_have_it_now_carries_on_with_the_questions(page_case):
    page = page_case("OPENAI_API_KEY=sk-test-openai\n")
    next(b for b in page.button if b.label == "I don't have it now").click().run()
    assert not page.exception
    assert answer_box(page)  # the questions continue
    assert not page.checkbox  # and the photo step is not asked again


def test_page_after_a_photo_says_thank_you_and_carries_on(page_case):
    page = page_case("OPENAI_API_KEY=sk-test-openai\n", with_photo=True)
    assert not page.exception
    assert any("Your W-2 photo is added" in s.value for s in page.success)
    assert [e.label for e in page.expander] == ["Add another W-2"]
    assert answer_box(page)


def test_page_without_a_key_says_a_volunteer_will_help(page_case):
    page = page_case("")
    assert not page.exception
    assert any("Reading photos is not set up" in m.value for m in page.markdown)
    assert not page.checkbox
    assert answer_box(page)  # nothing to wait for: the questions carry on


def test_the_questions_wait_for_the_photo_only_until_one_is_chosen(service):
    graph = service.graph
    answer_until_the_w2_question_is_answered(graph)
    assert chat.waiting_for_w2(graph, CASE)
    assert not chat.waiting_for_w2(graph, CASE, later=True)  # "I don't have it now"
    assert chat.add_w2(service, CASE, W2_PHOTO, confirmed=True) is None
    assert not chat.waiting_for_w2(graph, CASE)  # a photo is in
    assert chat.show_w2_upload(graph, CASE)  # another W-2 can still be added


def test_a_reading_failure_is_logged_with_its_cause_but_without_a_traceback(caplog):
    import logging

    with caplog.at_level(logging.WARNING, logger="silverfile.chat"):
        chat.note_reading_failure(SafeInputError("The provider refused\nthe request " + "x" * 400))
    [record] = caplog.records
    assert "SafeInputError" in record.getMessage() and "\n" not in record.getMessage()
    assert len(record.getMessage()) < 400 and record.exc_info is None
