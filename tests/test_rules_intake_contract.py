"""Rules must understand the facts Intake writes (docs/intake-rules-contract.md).

Intake (Supriya, docs/answer-names.md) is the source of truth for fact names and value shapes;
Rules adapts. These were strict expected failures until Matthew's Rules read Intake's names;
they are now plain regression tests.
"""
import pytest

from src.agents import rules


def eligibility(facts):
    return rules.run({"facts": {k: {"value": v, "source": "user"} for k, v in facts.items()},
                      "extracted": {}}, None)["eligibility"]


def test_sanity_rules_decides_a_single_filer_from_intakes_names():
    result = eligibility({"taxpayer_birth_date": "1950-03-04", "married_dec31": "no",
                          "household_situation": "single"})
    assert result["eligible_1040sr"] is True and result["filing_status"] == "single"


def test_a_no_answer_to_blindness_is_not_counted_as_blind():
    result = eligibility({"taxpayer_birth_date": "1950-03-04", "married_dec31": "no",
                          "household_situation": "single", "taxpayer_blind": "no"})
    assert result["age_blindness_boxes"] == 1


def test_rules_finds_the_birth_date_under_intakes_name():
    result = eligibility({"taxpayer_birth_date": "1950-03-04", "household_situation": "single",
                          "married_dec31": "no"})
    assert result["eligible_1040sr"] is True
