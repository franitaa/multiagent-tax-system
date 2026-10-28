"""Focused tests for the Eligibility & Rules Agent."""
import pytest

from src.agents.rules import run
from src.state import (
    EXPLOITATION_SIGNS,
    FILING_STATUS_AMBIGUITY,
    FORM_1099R_BOX_2B,
    OUT_OF_SCOPE,
    TAX_ADVICE_REQUEST,
)


def fact(value, source="user"):
    return {"value": value, "source": source}


def make_view(*, facts=None, extracted=None, escalation=None, human_decisions=None):
    return {
        "facts": facts or {},
        "extracted": extracted or {},
        "session_summary": "",
        "escalation": escalation,
        "human_decisions": human_decisions or [],
    }


def single_facts(**overrides):
    facts = {
        "taxpayer_birth_date": fact("1950-05-10"),
        "married_dec31": fact("no"),
        "household_situation": fact("single"),
        "taxpayer_blind": fact("no"),
        "us_resident_all_year": fact("yes"),
    }
    facts.update(overrides)
    return facts


def mfj_facts(**overrides):
    facts = {
        "taxpayer_birth_date": fact("1950-05-10"),
        "spouse_birth_date": fact("1965-08-20"),
        "married_dec31": fact("yes"),
        "file_jointly": fact("yes"),
        "taxpayer_blind": fact("no"),
        "spouse_blind": fact("no"),
        "spouse_can_be_claimed": fact("no"),
        "us_resident_all_year": fact("yes"),
    }
    facts.update(overrides)
    return facts


def test_single_taxpayer_is_eligible():
    result = run(make_view(facts=single_facts()), tools={})
    assert result["eligibility"]["filing_status"] == "single"
    assert result["eligibility"]["eligible_1040sr"] is True
    assert result["eligibility"]["in_scope"] is True
    assert result["handoff_request"]["to"] == "computation"


def test_exact_dob_rule_before_cutoff_is_eligible():
    facts = single_facts(
        taxpayer_birth_date=fact("1961-01-01"),
    )
    result = run(make_view(facts=facts), tools={})
    assert result["eligibility"]["eligible_1040sr"] is True


def test_exact_dob_rule_on_cutoff_is_not_eligible():
    facts = single_facts(
        taxpayer_birth_date=fact("1961-01-02"),
    )
    result = run(make_view(facts=facts), tools={})
    assert result["eligibility"]["eligible_1040sr"] is False
    assert result["eligibility"]["in_scope"] is False
    assert result["escalation"]["condition"] == OUT_OF_SCOPE


def test_mfj_spouse_can_make_return_eligible():
    facts = mfj_facts(
        taxpayer_birth_date=fact("1965-01-01"),
        spouse_birth_date=fact("1950-01-01"),
    )
    result = run(make_view(facts=facts), tools={})
    assert result["eligibility"]["filing_status"] == "mfj"
    assert result["eligibility"]["taxpayer_qualifies"] is False
    assert result["eligibility"]["spouse_qualifies"] is True
    assert result["eligibility"]["eligible_1040sr"] is True


def test_rules_derives_mfs_from_plain_intake_answers():
    facts = mfj_facts(
        file_jointly=fact("no"),
        spouse_itemizing=fact("no"),
    )
    result = run(make_view(facts=facts), tools={})
    assert result["eligibility"]["filing_status"] == "mfs"
    assert result["handoff_request"]["to"] == "computation"


def test_human_filing_status_override_takes_precedence():
    facts = {
        "taxpayer_birth_date": fact("1950-05-10"),
        "married_dec31": fact("no"),
        "household_situation": fact("widowed"),
        "spouse_death_year": fact(2023),
        "filing_status": fact(
            "qss",
            source="human:FILING_STATUS_AMBIGUITY",
        ),
        "taxpayer_blind": fact("no"),
        "us_resident_all_year": fact("yes"),
    }
    result = run(make_view(facts=facts), tools={})
    assert result["eligibility"]["filing_status"] == "qss"
    assert result["handoff_request"]["to"] == "computation"


def test_missing_birth_date_returns_to_intake():
    facts = {
        "married_dec31": fact("no"),
        "household_situation": fact("single"),
        "taxpayer_blind": fact("no"),
    }
    result = run(make_view(facts=facts), tools={})
    assert result["handoff_request"]["to"] == "intake"
    assert "taxpayer_birth_date" in result["handoff_request"]["reason"]


def test_missing_filing_answers_escalate_as_ambiguous():
    facts = {
        "taxpayer_birth_date": fact("1950-05-10"),
        "taxpayer_blind": fact("no"),
    }
    result = run(make_view(facts=facts), tools={})
    assert result["escalation"]["condition"] == FILING_STATUS_AMBIGUITY
    assert result["handoff_request"]["to"] == "human"


def test_no_blindness_does_not_add_box():
    result = run(make_view(facts=single_facts()), tools={})
    assert result["eligibility"]["age_blindness_boxes"] == 1


def test_yes_blindness_adds_box():
    facts = single_facts(taxpayer_blind=fact("yes"))
    result = run(make_view(facts=facts), tools={})
    assert result["eligibility"]["age_blindness_boxes"] == 2


def test_not_sure_blindness_returns_to_intake():
    facts = single_facts(taxpayer_blind=fact("not_sure"))
    result = run(make_view(facts=facts), tools={})
    assert result["handoff_request"]["to"] == "intake"
    assert "taxpayer_blind" in result["handoff_request"]["reason"]


def test_mfj_age_blindness_boxes_include_relevant_spouse():
    facts = mfj_facts(
        spouse_birth_date=fact("1950-08-20"),
        taxpayer_blind=fact("yes"),
        spouse_blind=fact("yes"),
    )
    result = run(make_view(facts=facts), tools={})
    assert result["eligibility"]["age_blindness_boxes"] == 4


@pytest.mark.parametrize(
    ("field_name", "reason_text"),
    [
        ("sold_stocks_or_property", "Stocks"),
        ("business_or_rental_income", "Business"),
        ("foreign_income_or_accounts", "Foreign"),
        ("digital_assets", "Digital"),
        ("has_other_tax_forms", "Other tax forms"),
        ("can_be_claimed_as_dependent", "claimed as a dependent"),
    ],
)
def test_yes_scope_screening_answer_escalates(field_name, reason_text):
    facts = single_facts(**{field_name: fact("yes")})
    result = run(make_view(facts=facts), tools={})
    assert result["eligibility"]["in_scope"] is False
    assert result["escalation"]["condition"] == OUT_OF_SCOPE
    assert reason_text.lower() in result["escalation"]["reason"].lower()


def test_not_sure_scope_answer_escalates_as_out_of_scope():
    facts = single_facts(digital_assets=fact("not_sure"))
    result = run(make_view(facts=facts), tools={})
    assert result["eligibility"]["in_scope"] is False
    assert result["escalation"]["condition"] == OUT_OF_SCOPE
    assert "not_sure" in result["escalation"]["reason"]


def test_not_us_resident_all_year_is_out_of_scope():
    facts = single_facts(us_resident_all_year=fact("no"))
    result = run(make_view(facts=facts), tools={})
    assert result["eligibility"]["in_scope"] is False
    assert result["escalation"]["condition"] == OUT_OF_SCOPE


def test_mfs_spouse_itemizing_is_out_of_scope():
    facts = mfj_facts(
        file_jointly=fact("no"),
        spouse_itemizing=fact("yes"),
    )
    result = run(make_view(facts=facts), tools={})
    assert result["eligibility"]["filing_status"] == "mfs"
    assert result["eligibility"]["in_scope"] is False
    assert result["escalation"]["condition"] == OUT_OF_SCOPE


def test_spouse_can_be_claimed_is_out_of_scope_for_joint_return():
    facts = mfj_facts(spouse_can_be_claimed=fact("yes"))
    result = run(make_view(facts=facts), tools={})
    assert result["eligibility"]["in_scope"] is False
    assert result["escalation"]["condition"] == OUT_OF_SCOPE


def test_1099r_box_2b_from_extracted_document_escalates():
    extracted = {
        "doc-1": {
            "kind": "1099-R",
            "fields": {
                "box_2b": {
                    "value": "yes",
                    "source": "doc-1",
                }
            },
        }
    }
    result = run(
        make_view(
            facts=single_facts(),
            extracted=extracted,
        ),
        tools={},
    )
    assert result["eligibility"]["in_scope"] is False
    assert result["escalation"]["condition"] == FORM_1099R_BOX_2B


def test_ssa1099_adds_social_security_rule():
    extracted = {
        "doc-ssa": {
            "kind": "SSA-1099",
            "fields": {},
        }
    }
    result = run(
        make_view(
            facts=single_facts(),
            extracted=extracted,
        ),
        tools={},
    )
    assert (
        "Taxable Social Security worksheet"
        in result["eligibility"]["applicable_rules"]
    )


def test_existing_intake_tax_advice_escalation_is_preserved():
    escalation = {
        "pending": True,
        "condition": TAX_ADVICE_REQUEST,
        "reason": "Taxpayer requested advice",
        "raised_by": "intake",
    }
    result = run(
        make_view(
            facts=single_facts(),
            escalation=escalation,
        ),
        tools={},
    )
    assert result["escalation"] == escalation
    assert result["handoff_request"]["to"] == "human"


def test_existing_intake_exploitation_escalation_is_preserved():
    escalation = {
        "pending": True,
        "condition": EXPLOITATION_SIGNS,
        "reason": "Third-party pressure detected",
        "raised_by": "intake",
    }
    result = run(
        make_view(
            facts=single_facts(),
            escalation=escalation,
        ),
        tools={},
    )
    assert result["escalation"] == escalation
    assert result["handoff_request"]["to"] == "human"


def test_caring_for_someone_requires_filing_status_review():
    facts = single_facts(
        household_situation=fact("caring_for_someone"),
    )
    result = run(make_view(facts=facts), tools={})
    assert result["escalation"]["condition"] == FILING_STATUS_AMBIGUITY


def test_widowed_requires_filing_status_review():
    facts = single_facts(
        household_situation=fact("widowed"),
        spouse_death_year=fact(2023),
    )
    result = run(make_view(facts=facts), tools={})
    assert result["escalation"]["condition"] == FILING_STATUS_AMBIGUITY


def test_resolved_out_of_scope_is_not_raised_again():
    facts = single_facts(business_or_rental_income=fact("yes"))
    decisions = [
        {
            "condition": OUT_OF_SCOPE,
            "decision": "continue",
        }
    ]
    result = run(
        make_view(
            facts=facts,
            human_decisions=decisions,
        ),
        tools={},
    )
    assert "escalation" not in result
    assert result["eligibility"]["in_scope"] is False
    assert result["handoff_request"]["to"] == "computation"
