"""Amounts the taxpayer typed in (estimated payments, adjustments) must pass Review.

Review accepts a typed amount only with the source "direct user input" (docs/answer-names.md). The provenance
helper used another label, so any case where the taxpayer typed one of these amounts failed Review, hit the
review bound and stopped as REVIEW_BOUND_EXCEEDED. These tests run real Computation and real Review.
"""
import pytest

from provenance import make_direct_input_provenance
from src.graph import build_graph
from src.scenarios import clean_case
from tests.helpers import cfg

BASE = {"taxpayer_birth_date": "1950-03-04", "married_dec31": "no", "household_situation": "single", "has_w2": "yes"}


def run(tmp_path, **typed):
    facts = {k: {"value": v, "source": "user"} for k, v in {**BASE, **typed}.items()}

    def intake(view, tools):
        return {"facts": facts, "pending_question": None, "intake_complete": True,
                "handoff_request": {"to": "extraction", "reason": "intake complete"}}
    return build_graph(trace_dir=tmp_path, agents={"intake": intake}).invoke(clean_case(), cfg("t"))


def test_the_helper_uses_the_agreed_label():
    record = make_direct_input_provenance(500, "estimated_payments_amount", "taxpayer (via Intake)")
    assert record["source"] == "direct user input"


@pytest.mark.parametrize("fact, line", [("estimated_payments_amount", "line_26"), ("adjustments_amount", "line_10")])
def test_a_typed_amount_passes_review_and_the_case_completes(tmp_path, fact, line):
    result = run(tmp_path, **{fact: 500})
    assert "__interrupt__" not in result, [i.value["condition"] for i in result["__interrupt__"]]
    assert result["status"] == "complete" and result["review"]["verdict"] == "pass"
    assert result["computed"][line]["value"] == 500
