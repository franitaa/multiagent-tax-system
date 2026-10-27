"""Rules must understand the facts Intake writes (docs/intake-rules-contract.md).

Intake (Supriya, docs/answer-names.md) is the source of truth for fact names and value shapes;
Rules adapts. Each test below fails today for the reason in its marker. They are STRICT
expected failures: when Rules is fixed the test passes, strict mode fails the run, and the
marker should be removed.
"""
import pytest

from src.agents import rules


def eligibility(facts):
    return rules.run({"facts": {k: {"value": v, "source": "user"} for k, v in facts.items()},
                      "extracted": {}}, None)["eligibility"]


def test_sanity_rules_works_with_the_names_it_reads_today():
    result = eligibility({"taxpayer_birth_date": "1950-03-04", "household_situation": "single",
                          "married_dec31": "no"})
    assert result["eligible_1040sr"] is True and result["filing_status"] == "single"


@pytest.mark.xfail(strict=True, raises=AssertionError, reason=(
    "Rules counts Intake's string answer 'no' as blind: it runs bool(taxpayer_blind) on the "
    "string, and bool('no') is True. Born 1950 and not blind should give 1 age/blindness box, "
    "Rules gives 2 (an overstated deduction). Parse yes/no/not_sure strings; see the contract doc."))
def test_a_no_answer_to_blindness_is_not_counted_as_blind():
    result = eligibility({"taxpayer_dob": "1950-03-04", "filing_status_claim": "single",
                          "taxpayer_blind": "no"})
    assert result["age_blindness_boxes"] == 1


def test_rules_finds_the_birth_date_under_intakes_name():
    result = eligibility({"taxpayer_birth_date": "1950-03-04", "household_situation": "single",
                          "married_dec31": "no"})
    assert result["eligible_1040sr"] is True


def test_a_volunteers_full_name_filing_status_from_the_human_gate_is_honored():
    """The human gate writes `married_filing_jointly`; Rules works in codes (`mfj`)."""
    result = rules.run({"facts": {
        "taxpayer_birth_date": {"value": "1950-03-04", "source": "user"},
        "married_dec31": {"value": "no", "source": "user"},
        "household_situation": {"value": "single", "source": "user"},
        "filing_status": {"value": "married_filing_jointly", "source": "human:FILING_STATUS_AMBIGUITY"},
    }, "extracted": {}}, None)["eligibility"]
    assert result["filing_status"] == "mfj"
