"""Table-driven test of the pure router: one row per routing rule, built from real state
through routing_view so the projection is exercised too."""
import copy

import pytest

from src import state as S
from src.orchestration.context import routing_view
from src.orchestration.router import route
from src.scenarios import document


def st(**over):
    """A state that has just finished intake, then overrides."""
    base = {
        "messages": [{"role": "user", "content": "hi"}] * 2,
        "intake_complete": True,
        "documents": [document()],
    }
    return {**base, **over}


EXTRACTED = {"doc-1": {"doc_id": "doc-1"}}
ELIGIBLE = {"in_scope": True, "filing_status": "single", "citations": ["x"]}
LINES = {"line_1a": {"value": 1.0}}
ESC = {"pending": True, "condition": S.TAX_ADVICE_REQUEST, "reason": "r", "raised_by": "intake"}

TABLE = [
    # (id, state, expected next)
    ("1 escalation pending", st(escalation=ESC), "human"),
    ("1 escalation beats pending documents", st(escalation=ESC, extracted={}), "human"),
    ("1 escalation beats done", st(escalation=ESC, done=True), "human"),
    ("3 done", st(done=True), "end"),
    ("3a yield after intake question", st(intake_complete=False, pending_question="q?"), "end"),
    ("3a still waiting", st(intake_complete=False, pending_question="q?", awaiting_since_msgs=2), "end"),
    ("3a user replied", st(intake_complete=False, pending_question="q?", awaiting_since_msgs=1), "intake"),
    ("4 intake incomplete", st(intake_complete=False), "intake"),
    ("5 documents pending", st(), "extraction"),
    ("6 no eligibility", st(extracted=EXTRACTED), "rules"),
    ("7 out of scope", st(extracted=EXTRACTED, eligibility={"in_scope": False}), "human"),
    ("7 out of scope then human stop ends the case", st(
        extracted=EXTRACTED, eligibility={"in_scope": False}, done=True), "end"),
    ("8 no computed lines", st(extracted=EXTRACTED, eligibility=ELIGIBLE), "computation"),
    ("9 not reviewed", st(extracted=EXTRACTED, eligibility=ELIGIBLE, computed=LINES), "review"),
    ("12 review passed", st(extracted=EXTRACTED, eligibility=ELIGIBLE, computed=LINES,
                            review={"verdict": "pass"}), "end"),
]


@pytest.mark.parametrize("state,expected", [c[1:] for c in TABLE], ids=[c[0] for c in TABLE])
def test_routing_table(state, expected):
    assert route(routing_view(state)).next == expected


def test_side_effects_are_returned_not_applied():
    out = route(routing_view(st(extracted=EXTRACTED, eligibility={"in_scope": False})))
    assert out.update["status"] == S.AWAITING_HUMAN
    assert out.update["escalation"]["condition"] == S.OUT_OF_SCOPE
    done = route(routing_view(st(extracted=EXTRACTED, eligibility=ELIGIBLE, computed=LINES,
                                 review={"verdict": "pass"})))
    assert done.update == {"done": True, "status": S.COMPLETE}
    yielded = route(routing_view(st(intake_complete=False, pending_question="q?")))
    assert yielded.update == {"status": S.AWAITING_USER, "awaiting_since_msgs": 2}
    answered = route(routing_view(st(intake_complete=False, pending_question="q?",
                                     awaiting_since_msgs=1)))
    assert answered.update == {"awaiting_since_msgs": None, "pending_question": None,
                               "status": S.RUNNING}


def test_route_is_pure():
    view = routing_view(st(extracted=EXTRACTED, eligibility={"in_scope": False}))
    before = copy.deepcopy(view)
    first, second = route(view), route(view)
    assert view == before and first == second


def test_review_fail_is_not_silently_handled_yet():
    state = st(extracted=EXTRACTED, eligibility=ELIGIBLE, computed=LINES, review={"verdict": "fail"})
    with pytest.raises(NotImplementedError):
        route(routing_view(state))
