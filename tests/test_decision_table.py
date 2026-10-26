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
FAIL = {"verdict": "fail", "findings": [{"line": "line_1a", "issue": "TEST"}],
        "send_back_to": "computation"}
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
    ("9 stale verdict cleared by a send-back: review again, not computation",
     st(extracted=EXTRACTED, eligibility=ELIGIBLE, computed=LINES, revision_count=1,
        pending_revision={"target": "computation", "round": 1, "findings": []}), "review"),
    ("10 review failed, rounds left", st(extracted=EXTRACTED, eligibility=ELIGIBLE, computed=LINES,
                                         review=FAIL, revision_count=0), "computation"),
    ("10 last allowed round (2 of 3 used)", st(extracted=EXTRACTED, eligibility=ELIGIBLE, computed=LINES,
                                               review=FAIL, revision_count=2), "computation"),
    ("10 asked to send back to rules: only computation supported", st(
        extracted=EXTRACTED, eligibility=ELIGIBLE, computed=LINES,
        review={**FAIL, "send_back_to": "rules"}), "computation"),
    ("11 bound reached (3 of 3)", st(extracted=EXTRACTED, eligibility=ELIGIBLE, computed=LINES,
                                     review=FAIL, revision_count=3), "human"),
    ("11 custom bound reached (1 of 1)", st(extracted=EXTRACTED, eligibility=ELIGIBLE, computed=LINES,
                                            review=FAIL, revision_count=1, max_revisions=1), "human"),
    ("11 bound of zero escalates on the first fail", st(
        extracted=EXTRACTED, eligibility=ELIGIBLE, computed=LINES, review=FAIL, max_revisions=0), "human"),
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


def test_send_back_update_clears_the_stale_verdict_and_counts_the_round():
    out = route(routing_view(st(extracted=EXTRACTED, eligibility=ELIGIBLE, computed=LINES,
                                review=FAIL, revision_count=1)))
    assert out.next == "computation" and "round 2 of 3" in out.reason
    assert out.update["review"] is None
    assert out.update["revision_count"] == 2
    assert out.update["pending_revision"] == {
        "target": "computation", "round": 2, "findings": FAIL["findings"]}
    assert out.update["review_history"] == [{
        "round": 2, "requested": "computation", "sent_to": "computation",
        "findings": FAIL["findings"]}]


def test_review_after_send_back_drops_the_revision_request():
    out = route(routing_view(st(extracted=EXTRACTED, eligibility=ELIGIBLE, computed=LINES,
                                revision_count=1, pending_revision={"target": "computation"})))
    assert out.next == "review" and out.update["pending_revision"] is None


def test_bound_exceeded_raises_an_orchestrator_escalation():
    out = route(routing_view(st(extracted=EXTRACTED, eligibility=ELIGIBLE, computed=LINES,
                                review=FAIL, revision_count=3)))
    assert out.update["escalation"]["condition"] == S.REVIEW_BOUND_EXCEEDED
    assert out.update["escalation"]["raised_by"] == "orchestrator"
    assert out.update["status"] == S.AWAITING_HUMAN


def test_invalid_verdict_is_an_error_not_a_guess():
    state = st(extracted=EXTRACTED, eligibility=ELIGIBLE, computed=LINES, review={"verdict": "maybe"})
    with pytest.raises(ValueError, match="invalid review verdict"):
        route(routing_view(state))
