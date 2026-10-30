"""Tests for the volunteer dashboard logic (src/ui/dashboard_data.py)."""
from datetime import datetime, timedelta, timezone

import pytest

from src import state as S
from src.orchestration.human import FILING_STATUSES
from src.ui import chat_session as chat
from src.ui import dashboard_data as dash
from tests.test_intake_agent import NAME


@pytest.fixture
def graph(tmp_path, monkeypatch):
    monkeypatch.setattr(dash, "TRACE_DIR", str(tmp_path))  # the audit log the graph writes to
    return chat.make_graph(trace_dir=tmp_path)


def start(graph, case_id, *answers):
    chat.start(graph, case_id)
    for answer in [NAME, *answers]:
        chat.send(graph, case_id, answer)


def test_no_cases_yet(graph):
    assert dash.all_cases(graph) == []


def test_a_case_shows_its_name_and_status(graph):
    start(graph, "SF-100-001", "no")
    [row] = dash.all_cases(graph)
    assert row["case_id"] == "SF-100-001"
    assert row["name"] == NAME
    assert row["status"] == dash.ANSWERING
    assert row["condition"] is None


def test_a_case_needing_a_volunteer_is_listed_first(graph):
    start(graph, "SF-100-002", "no")
    start(graph, "SF-100-003", "Should I file jointly?")
    start(graph, "SF-100-004", "no", "single")
    rows = dash.all_cases(graph)
    assert rows[0]["case_id"] == "SF-100-003"
    assert rows[0]["status"] == dash.NEEDS_VOLUNTEER
    assert rows[0]["alarm"] == "The taxpayer asked for tax advice."
    assert dash.counts(rows)[dash.NEEDS_VOLUNTEER] == 1
    assert dash.counts(rows)[dash.ANSWERING] == 2


def test_continue_needs_a_note_and_the_gate_says_why(graph):
    start(graph, "SF-100-005", "Should I file jointly?")
    waiting = dash.pending(graph, "SF-100-005")
    assert waiting["options"] == ["continue", "stop"]
    error = dash.resolve(graph, "SF-100-005", "continue", "", "Pat Volunteer")
    assert "note" in error
    assert dash.case_summary(graph, "SF-100-005")["status"] == dash.NEEDS_VOLUNTEER  # still waiting


def test_continue_with_a_note_lets_the_taxpayer_carry_on(graph):
    start(graph, "SF-100-006", "Should I file jointly?")
    assert dash.resolve(graph, "SF-100-006", "continue", "Noted the question for the preparer.",
                        "Pat Volunteer") is None
    assert dash.case_summary(graph, "SF-100-006")["status"] == dash.ANSWERING
    assert chat.screen(graph, "SF-100-006") == chat.ASKING  # the chat page lets them answer again
    decision = graph.get_state({"configurable": {"thread_id": "SF-100-006"}}).values["human_decisions"][-1]
    assert decision["reviewer"] == "Pat Volunteer"
    assert decision["note"] == "Noted the question for the preparer."


def test_pressure_can_only_be_stopped(graph):
    start(graph, "SF-100-007", "He keeps my refund")
    waiting = dash.pending(graph, "SF-100-007")
    assert waiting["condition"] == S.EXPLOITATION_SIGNS
    assert waiting["options"] == ["stop"]
    assert dash.resolve(graph, "SF-100-007", "continue", "looks fine", "Pat Volunteer")  # refused
    assert dash.resolve(graph, "SF-100-007", "stop", "Called the taxpayer back alone.", "Pat Volunteer") is None
    assert dash.case_summary(graph, "SF-100-007")["status"] == dash.STOPPED


def test_the_taxpayers_own_words_are_in_the_notes(graph):
    start(graph, "SF-100-008", "He keeps my refund")
    assert any(n.get("taxpayer_words") == "He keeps my refund" for n in dash.volunteer_notes(graph, "SF-100-008"))


def test_spouse_died_offers_the_filing_statuses(graph):
    start(graph, "SF-100-009", "My husband passed away in March")
    waiting = dash.pending(graph, "SF-100-009")
    assert waiting["condition"] == S.FILING_STATUS_AMBIGUITY
    assert set(dash.choices(waiting)) == set(FILING_STATUSES)
    assert dash.resolve(graph, "SF-100-009", "continue", "Spoke with the taxpayer.", "Pat Volunteer",
                        {"filing_status": "married_filing_jointly"}) is None


def test_a_wrong_choice_is_refused_with_a_reason(graph):
    start(graph, "SF-100-010", "My husband passed away in March")
    error = dash.resolve(graph, "SF-100-010", "continue", "Spoke with the taxpayer.", "Pat Volunteer",
                         {"filing_status": "widow"})
    assert "filing_status" in error


def test_quiet_requests_for_a_volunteer_are_shown(graph):
    start(graph, "SF-100-014", "no")
    start(graph, "SF-100-015", "I'm not sure")  # married? not sure: noted, the chat carries on
    start(graph, "SF-100-016", "Can I talk to a real person?")
    rows = dash.all_cases(graph)
    assert [r["case_id"] for r in rows][:2] == ["SF-100-016", "SF-100-015"]  # the request first
    asked, unsure = rows[0], rows[1]
    assert asked["status"] == unsure["status"] == dash.ANSWERING  # neither paused the chat
    assert dash.open_questions_text(asked).startswith("Asked to talk to a volunteer")
    assert dash.open_questions_text(unsure) == "1 answer for a volunteer to check"
    assert dash.open_questions_text(rows[2]) == ""
    assert dash.counts(rows)[dash.OPEN_QUESTIONS] == 2


def test_an_answer_given_later_closes_the_question(graph):
    start(graph, "SF-100-017", "I'm not sure")
    chat.send(graph, "SF-100-017", "go back")
    chat.send(graph, "SF-100-017", "no")
    assert dash.case_summary(graph, "SF-100-017")["open_questions"] == 0


def test_needs_breakdown_and_filters(graph):
    start(graph, "SF-100-020", "Should I file jointly?")
    start(graph, "SF-100-021", "Can I deduct my medicine?")
    start(graph, "SF-100-022", "He keeps my refund")
    start(graph, "SF-100-023", "Can I talk to a real person?")
    start(graph, "SF-100-024", "no")
    rows = dash.all_cases(graph)
    assert dash.needs_breakdown(rows) == {"Tax advice question": 2, "Possible pressure": 1,
                                          "Asked for a person / not sure": 1}
    shown = lambda show, search="": [r["case_id"] for r in rows if dash.matches(r, show, search)]
    assert len(shown("All")) == 5
    assert set(shown(dash.NEEDS_VOLUNTEER)) == {"SF-100-020", "SF-100-021", "SF-100-022"}
    assert shown(dash.OPEN_QUESTIONS) == ["SF-100-023"]
    assert shown("All", "sf-100-024") == ["SF-100-024"]
    assert len(shown("All", NAME.split()[0].lower())) == 5


def test_the_volunteer_must_give_their_name(graph):
    start(graph, "SF-100-011", "Should I file jointly?")
    assert "your name" in dash.resolve(graph, "SF-100-011", "continue", "Noted.", "  ")
    assert dash.case_summary(graph, "SF-100-011")["status"] == dash.NEEDS_VOLUNTEER


def test_continue_on_a_filing_status_alarm_needs_a_status(graph):
    start(graph, "SF-100-020", "My husband passed away in March")
    error = dash.resolve(graph, "SF-100-020", "continue", "Spoke with the taxpayer.", "Pat Volunteer")
    assert error == dash.CHOOSE_STATUS
    assert dash.pending(graph, "SF-100-020")["condition"] == S.FILING_STATUS_AMBIGUITY  # still waiting
    values = graph.get_state({"configurable": {"thread_id": "SF-100-020"}}).values
    assert not values.get("human_decisions") and "filing_status" not in values["facts"]
    # Stopping needs no status.
    assert dash.resolve(graph, "SF-100-020", "stop", "", "Pat Volunteer") is None


def test_a_second_volunteer_is_told_the_case_was_already_decided(graph):
    start(graph, "SF-100-021", "Should I file jointly?")
    seen = dash.pending(graph, "SF-100-021")["condition"]  # both volunteers opened the case
    assert dash.resolve(graph, "SF-100-021", "continue", "Noted.", "Pat Volunteer", condition=seen) is None
    assert dash.resolve(graph, "SF-100-021", "stop", "Stop it.", "Sam Volunteer",
                        condition=seen) == dash.NO_LONGER_WAITING
    decisions = graph.get_state({"configurable": {"thread_id": "SF-100-021"}}).values["human_decisions"]
    assert [d["reviewer"] for d in decisions] == ["Pat Volunteer"]  # only the first decision counts


def test_a_decision_for_an_alarm_that_is_no_longer_open_is_refused(graph):
    start(graph, "SF-100-022", "Should I file jointly?")
    assert dash.resolve(graph, "SF-100-022", "stop", "", "Pat Volunteer",
                        condition=S.EXPLOITATION_SIGNS) == dash.NO_LONGER_WAITING
    assert dash.pending(graph, "SF-100-022")["condition"] == S.TAX_ADVICE_REQUEST  # untouched


def test_the_draft_form_warns_when_a_form_was_not_read(graph):
    from src.agents import computation
    from src.orchestration.access import ToolBox

    start(graph, "SF-100-023", "no")
    extracted = {"doc-2": {"doc_id": "doc-2", "kind": "SSA-1099", "fields": {}, "status": "skipped"}}
    facts = {"filing_status": {"value": "single", "source": "user"}, "age": {"value": 70, "source": "user"}}
    computed = computation.run({"facts": facts, "extracted": extracted, "eligibility": {}},
                               ToolBox("computation"))["computed"]
    graph.update_state({"configurable": {"thread_id": "SF-100-023"}},
                       {"computed": computed, "extracted": extracted})
    page = dash.draft_form_html(graph, "SF-100-023")
    assert "Income is missing from this draft" in page and "SSA-1099" in page


def test_an_error_stop_has_words():
    assert dash.EVENT_WORDS["halted_by_error"] == "Stopped on an error"


def test_history_shows_who_decided_and_the_record_is_intact(graph):
    start(graph, "SF-100-012", "Should I file jointly?")
    dash.record_view("SF-100-012", "Pat Volunteer")
    dash.resolve(graph, "SF-100-012", "continue", "Noted for the preparer.", "Pat Volunteer")
    rows = dash.history("SF-100-012")
    whats = [r["what"] for r in rows]
    assert "Alarm raised" in whats and "Opened in the dashboard" in whats
    decided = next(r for r in rows if r["what"] == "Volunteer decided")
    assert decided["who"] == "volunteer:Pat Volunteer"
    assert S.TAX_ADVICE_REQUEST in decided["detail"] and "continue" in decided["detail"]
    assert dash.history_intact("SF-100-012")


def test_ssns_are_masked_in_the_answers(graph, monkeypatch):
    monkeypatch.setattr(chat, "answers", lambda g, c: [{"question": "SSN?", "answer": "900-11-2222"},
                                                        {"question": "Name?", "answer": "Ana"}])
    assert [r["answer"] for r in dash.answers(graph, "SF-100-013")] == ["•••-••-2222", "Ana"]


def test_cases_from_the_w2_page_are_labelled(graph):
    graph.update_state({"configurable": {"thread_id": "demo"}}, {"status": S.RUNNING})
    assert dash.case_summary(graph, "demo")["name"] == "(test case from the W-2 page)"


def test_every_alarm_has_plain_words():
    conditions = {v for k, v in vars(S).items() if k.isupper() and isinstance(v, str) and v.isupper()
                  and "_" in v and k == v}
    assert len(conditions) >= 10 and conditions <= set(dash.ALARMS)


def test_filing_status_words_match_the_gate():
    assert set(dash.FILING_STATUS_WORDS) == set(FILING_STATUSES)


@pytest.mark.parametrize("delta, words", [
    (timedelta(seconds=20), "just now"), (timedelta(minutes=1), "1 minute ago"),
    (timedelta(minutes=5), "5 minutes ago"), (timedelta(hours=2), "2 hours ago"),
    (timedelta(days=3), "3 days ago"),
])
def test_time_ago(delta, words):
    now = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)
    assert dash.time_ago((now - delta).isoformat(), now) == words
