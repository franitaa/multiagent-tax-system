"""Intake asks the amounts on the forms Extraction does not read (issue #27, step 2): SSA-1099,
1099-INT, 1099-DIV. Asked only after "yes" to the form, stored as typed amounts, used by Computation."""
import sys
import tempfile
from pathlib import Path

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from src import state as S
from src.agents import intake_agent
from src.income_forms import TYPED_AMOUNTS
from src.ui import chat_session as chat
from tests.test_intake_agent import FULL_ANSWERS

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests_p3"))
from p3_helpers import FakeReader  # noqa: E402  (offline stand-in for the AI reader)

AMOUNT_QUESTIONS = {q.fact: q for q in intake_agent.AFTER_DEPENDENTS if q.fact in TYPED_AMOUNTS}


def test_every_typed_amount_computation_reads_has_a_question():
    assert set(AMOUNT_QUESTIONS) == set(TYPED_AMOUNTS)
    assert all(q.kind == intake_agent.AMOUNT for q in AMOUNT_QUESTIONS.values())


def interview(tmp_path, form=None, amounts=None):
    """The full chat interview; `form` is answered "yes" and its boxes get `amounts` (by box)."""
    chat.RUNTIME = str(tmp_path / "runtime")
    service = chat.make_app_service(trace_dir=tmp_path, reader=FakeReader(), saved_sessions=InMemorySaver())
    graph, case = service.graph, chat.new_case_id()
    config = {"configurable": {"thread_id": case}}
    chat.start(graph, case)
    answers, asked = list(FULL_ANSWERS), []
    while chat.screen(graph, case) == chat.ASKING:
        question = graph.get_state(config).values["pending_question"].lower()
        if "what is the amount in box" in question:
            box = question.split("box ")[1].split(",")[0]
            asked.append(box)
            answer = (amounts or {}).get(box, "0")
        else:
            answer = answers.pop(0)
            if form and question.startswith("did you get") and form in question:
                answer = "yes"
        chat.send(graph, case, answer)
    return graph.get_state(config), asked


def test_with_no_such_forms_the_interview_is_unchanged(tmp_path):
    state, asked = interview(tmp_path)
    assert asked == []
    assert sum(m["role"] == "user" for m in state.values["messages"]) == len(FULL_ANSWERS)


@pytest.mark.parametrize("form, amounts, line, value", [
    ("ssa-1099", {"5": "24,000", "6": "300"}, "line_6a", 24000),
    ("1099-int", {"1": "250", "8": "0", "4": "25"}, "line_2b", 250),
    ("1099-div", {"1a": "400", "1b": "300", "4": "0"}, "line_3b", 400),
])
def test_typed_amounts_reach_the_draft_without_a_volunteer_pause(tmp_path, form, amounts, line, value):
    state, asked = interview(tmp_path, form, amounts)
    assert asked == list(amounts)  # every box of that form, once
    facts = state.values["facts"]
    typed = [n for n, (kind, _) in TYPED_AMOUNTS.items() if kind == form.replace("-", "")]
    assert all(facts[n]["source"] == "direct user input" for n in typed)
    # the photo of the W-2 was not added in this test, so the only pause is for the W-2 itself
    assert [i.value["condition"] for i in state.interrupts] == [S.INCOME_NOT_READ]
    assert "W-2" in state.interrupts[0].value["reason"] and form.upper() not in state.interrupts[0].value["reason"]


def test_not_sure_of_the_main_amount_skips_the_other_boxes_and_pauses(tmp_path):
    state, asked = interview(tmp_path, "ssa-1099", {"5": "not sure"})
    assert asked == ["5"]  # box 6 is not asked: a typed box 6 alone would count the form as read
    assert "ssa1099_withheld" not in state.values["facts"]
    reasons = " ".join(i.value["reason"] for i in state.interrupts)
    assert state.interrupts[0].value["condition"] == S.INCOME_NOT_READ and "SSA-1099" in reasons
