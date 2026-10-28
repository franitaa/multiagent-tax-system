"""Current Eligibility & Rules Agent contract tests (2025 Form 1040-SR).

Replaces the older tests/test_rules.py following the PR #21 changes:
- Rules emits eligibility['rule_citations'] (paired rule + policy citation).
- 'applicable_rules' and standalone 'citations' are no longer required.
- Unknown taxpayer/spouse blindness preserves confirmed age boxes and routes
  to Human Review, *not* back to Intake.

Run from your repository root:
    python -m pytest tests/test_rules.py -v

These are Rules unit tests. They do not prove the orchestrator actually pauses
on a handoff to Human Review; that needs a separate integration test.
"""

import pytest

from src.agents.rules import run
from src.state import (
    EXPLOITATION_SIGNS,
    FILING_STATUS_AMBIGUITY,
    FORM_1099R_BOX_2B,
    OUT_OF_SCOPE,
    SOURCE_CONFLICT,
    TAX_ADVICE_REQUEST,
)


def fact(value, source="user"):
    return {"value": value, "source": source}


def make_view(*, facts=None, extracted=None, escalation=None, human_decisions=None):
    return {
        "facts": facts if facts is not None else {},
        "extracted": extracted if extracted is not None else {},
        "session_summary": "",
        "escalation": escalation,
        "human_decisions": human_decisions if human_decisions is not None else [],
    }


def single_facts(**overrides):
    answers = {
        "taxpayer_birth_date": fact("1950-05-10"),
        "married_dec31": fact("no"),
        "household_situation": fact("single"),
        "taxpayer_blind": fact("no"),
        "us_resident_all_year": fact("yes"),
    }
    answers.update(overrides)
    return answers


def mfj_facts(**overrides):
    answers = {
        "taxpayer_birth_date": fact("1950-05-10"),
        "spouse_birth_date": fact("1952-08-20"),
        "married_dec31": fact("yes"),
        "file_jointly": fact("yes"),
        "taxpayer_blind": fact("no"),
        "spouse_blind": fact("no"),
        "spouse_can_be_claimed": fact("no"),
        "us_resident_all_year": fact("yes"),
    }
    answers.update(overrides)
    return answers


def evaluate(facts, **view_overrides):
    return run(make_view(facts=facts, **view_overrides), tools={})


def assert_citation(result, rule, section):
    pairs = result["eligibility"]["rule_citations"]
    assert {"rule": rule, "citation": f"policy.md §{section}"} in pairs


def assert_human_escalation(result, condition):
    assert result["handoff_request"]["to"] == "human"
    assert result["escalation"]["pending"] is True
    assert result["escalation"]["condition"] == condition


# --- Output contract and ordinary eligibility --------------------------------


def test_clean_single_taxpayer_is_eligible_and_goes_to_computation():
    result = evaluate(single_facts())
    eligibility = result["eligibility"]
    assert eligibility["filing_status"] == "single"
    assert eligibility["filing_status_valid"] is True
    assert eligibility["taxpayer_qualifies"] is True
    assert eligibility["eligible_1040sr"] is True
    assert eligibility["in_scope"] is True
    assert eligibility["age_blindness_boxes"] == 1
    assert result["handoff_request"]["to"] == "computation"


def test_output_contract_uses_paired_rule_citations_only():
    eligibility = evaluate(single_facts())["eligibility"]
    required = {
        "eligible_1040sr", "taxpayer_qualifies", "spouse_qualifies",
        "filing_status", "filing_status_valid", "age_blindness_boxes",
        "in_scope", "out_of_scope_reasons", "rule_citations",
    }
    assert required <= eligibility.keys()
    assert "applicable_rules" not in eligibility
    assert "citations" not in eligibility
    pairs = eligibility["rule_citations"]
    assert isinstance(pairs, list) and pairs
    assert all(set(item) == {"rule", "citation"} for item in pairs)
    assert len({item["rule"] for item in pairs}) == len(pairs)
    assert_citation({"eligibility": eligibility}, "Filing status validation", "2.2")
    assert_citation({"eligibility": eligibility}, "1040-SR eligibility", "2.1")
    assert_citation({"eligibility": eligibility}, "Standard deduction age/blindness rule", "2.3")
    assert_citation({"eligibility": eligibility}, "Standard deduction chart applicability", "2.4")


@pytest.mark.parametrize(
    ("birth_date", "expected"),
    [("1961-01-01", True), ("1961-01-02", False), ("1965-06-15", False)],
)
def test_1040sr_exact_birth_date_cutoff(birth_date, expected):
    result = evaluate(single_facts(taxpayer_birth_date=fact(birth_date)))
    assert result["eligibility"]["eligible_1040sr"] is expected
    if not expected:
        assert result["eligibility"]["in_scope"] is False
        assert_human_escalation(result, OUT_OF_SCOPE)


def test_mfj_spouse_alone_can_make_return_1040sr_eligible():
    facts = mfj_facts(
        taxpayer_birth_date=fact("1965-01-01"),
        spouse_birth_date=fact("1950-01-01"),
    )
    result = evaluate(facts)
    e = result["eligibility"]
    assert e["filing_status"] == "mfj"
    assert e["taxpayer_qualifies"] is False
    assert e["spouse_qualifies"] is True
    assert e["eligible_1040sr"] is True
    assert e["age_blindness_boxes"] == 1


def test_missing_date_returns_to_intake():
    facts = single_facts()
    del facts["taxpayer_birth_date"]
    result = evaluate(facts)
    assert result["handoff_request"]["to"] == "intake"
    assert "taxpayer_birth_date" in result["handoff_request"]["reason"]


@pytest.mark.parametrize("birth_date", ["not_sure", "invalid-date"])
def test_unresolved_taxpayer_birth_date_cannot_be_assumed(birth_date):
    result = evaluate(single_facts(taxpayer_birth_date=fact(birth_date)))
    assert result["eligibility"]["eligible_1040sr"] is None
    assert result["handoff_request"]["to"] == "intake"


def test_missing_filing_information_requires_human_review():
    result = evaluate({"taxpayer_birth_date": fact("1950-05-10")})
    assert_human_escalation(result, FILING_STATUS_AMBIGUITY)
    assert result["eligibility"]["filing_status"] == "undetermined"
    assert result["eligibility"]["filing_status_valid"] is False


@pytest.mark.parametrize("situation", ["caring_for_someone", "widowed"])
def test_complex_unmarried_status_requires_human_review(situation):
    facts = single_facts(household_situation=fact(situation))
    if situation == "widowed":
        facts["spouse_death_year"] = fact(2023)
    result = evaluate(facts)
    assert_human_escalation(result, FILING_STATUS_AMBIGUITY)


def test_mfs_is_derived_from_intake_answers():
    facts = mfj_facts(file_jointly=fact("no"), spouse_itemizing=fact("no"))
    result = evaluate(facts)
    assert result["eligibility"]["filing_status"] == "mfs"
    assert result["handoff_request"]["to"] == "computation"


@pytest.mark.parametrize(
    ("human_name", "short_code"),
    [
        ("married_filing_jointly", "mfj"),
        ("married_filing_separately", "mfs"),
        ("head_of_household", "hoh"),
        ("qualifying_surviving_spouse", "qss"),
    ],
)
def test_full_human_filing_status_names_are_normalized(human_name, short_code):
    facts = single_facts(
        filing_status=fact(human_name, "human:FILING_STATUS_AMBIGUITY"),
    )
    if short_code == "mfs":
        facts["spouse_itemizing"] = fact("no")
    result = evaluate(facts)
    assert result["eligibility"]["filing_status"] == short_code
    assert result["eligibility"]["filing_status_valid"] is True
    assert result["handoff_request"]["to"] == "computation"


def test_unreviewed_user_filing_status_is_not_a_human_override():
    facts = single_facts(filing_status=fact("head_of_household", "user"))
    result = evaluate(facts)
    assert result["eligibility"]["filing_status"] == "single"


# --- Age/blindness: PR #21 regression ---------------------------------------


@pytest.mark.parametrize(
    ("answer", "boxes", "destination"),
    [("no", 1, "computation"), ("yes", 2, "computation"), ("not_sure", 1, "human")],
)
def test_single_known_age_is_preserved_for_each_blindness_answer(answer, boxes, destination):
    result = evaluate(single_facts(taxpayer_blind=fact(answer)))
    assert result["eligibility"]["age_blindness_boxes"] == boxes
    assert result["handoff_request"]["to"] == destination
    if answer == "not_sure":
        assert "blind" in result["handoff_request"]["reason"].lower()
        assert_citation(result, "Uncertain blindness: human review", "3.3")


@pytest.mark.parametrize(
    ("spouse_answer", "boxes", "destination"),
    [("no", 2, "computation"), ("yes", 3, "computation"), ("not_sure", 2, "human")],
)
def test_joint_known_ages_preserved_for_spouse_blindness(spouse_answer, boxes, destination):
    result = evaluate(mfj_facts(spouse_blind=fact(spouse_answer)))
    assert result["eligibility"]["age_blindness_boxes"] == boxes
    assert result["handoff_request"]["to"] == destination
    if spouse_answer == "not_sure":
        assert "spouse" in result["handoff_request"]["reason"].lower()
        assert_citation(result, "Uncertain blindness: human review", "3.3")


def test_both_known_joint_ages_and_both_confirmed_blindness_count_four():
    result = evaluate(mfj_facts(taxpayer_blind=fact("yes"), spouse_blind=fact("yes")))
    assert result["eligibility"]["age_blindness_boxes"] == 4


def test_unknown_spouse_blindness_keeps_taxpayer_confirmed_blindness():
    result = evaluate(mfj_facts(taxpayer_blind=fact("yes"), spouse_blind=fact("not_sure")))
    assert result["eligibility"]["age_blindness_boxes"] == 3
    assert result["handoff_request"]["to"] == "human"


def test_irrelevant_spouse_blindness_is_ignored_for_single_filer():
    result = evaluate(single_facts(spouse_blind=fact("not_sure")))
    assert result["eligibility"]["age_blindness_boxes"] == 1
    assert result["handoff_request"]["to"] == "computation"


def test_mfs_age_boxes_include_spouse_when_applicable():
    result = evaluate(mfj_facts(file_jointly=fact("no"), spouse_itemizing=fact("no")))
    assert result["eligibility"]["filing_status"] == "mfs"
    assert result["eligibility"]["age_blindness_boxes"] == 2
    assert "Schedule 1-A enhanced senior deduction" not in {
        pair["rule"] for pair in result["eligibility"]["rule_citations"]
    }


def test_invalid_blindness_answer_returns_to_intake_without_discarding_age_box():
    result = evaluate(single_facts(taxpayer_blind=fact("maybe")))
    assert result["eligibility"]["age_blindness_boxes"] == 1
    assert result["handoff_request"]["to"] == "intake"


# --- Scope screening and document evidence -----------------------------------


@pytest.mark.parametrize(
    ("field", "reason_fragment"),
    [
        ("has_other_tax_forms", "Other tax forms"),
        ("sold_stocks_or_property", "Stocks"),
        ("business_or_rental_income", "Business"),
        ("foreign_income_or_accounts", "Foreign"),
        ("digital_assets", "Digital"),
        ("can_be_claimed_as_dependent", "claimed as a dependent"),
    ],
)
def test_yes_out_of_scope_screening_escalates_with_citation(field, reason_fragment):
    result = evaluate(single_facts(**{field: fact("yes")}))
    assert result["eligibility"]["in_scope"] is False
    assert_human_escalation(result, OUT_OF_SCOPE)
    assert reason_fragment.lower() in result["escalation"]["reason"].lower()
    assert_citation(result, "Out-of-scope screening", "3.1")


def test_not_sure_scope_screening_currently_escalates_out_of_scope():
    # This reflects current Rules behavior, NOT a completed clarify-once flow.
    result = evaluate(single_facts(digital_assets=fact("not_sure")))
    assert result["eligibility"]["in_scope"] is False
    assert_human_escalation(result, OUT_OF_SCOPE)
    assert "not_sure" in result["escalation"]["reason"]


def test_not_full_year_us_resident_is_out_of_scope():
    result = evaluate(single_facts(us_resident_all_year=fact("no")))
    assert result["eligibility"]["in_scope"] is False
    assert_human_escalation(result, OUT_OF_SCOPE)


@pytest.mark.parametrize(("answer", "expected"), [("yes", True), ("not_sure", True), ("no", False)])
def test_spouse_can_be_claimed_screening_for_joint_return(answer, expected):
    result = evaluate(mfj_facts(spouse_can_be_claimed=fact(answer)))
    assert result["eligibility"]["in_scope"] is (not expected)
    if expected:
        assert_human_escalation(result, OUT_OF_SCOPE)


@pytest.mark.parametrize(("answer", "expected"), [("yes", True), ("not_sure", True), ("no", False)])
def test_mfs_spouse_itemizing_screening(answer, expected):
    facts = mfj_facts(file_jointly=fact("no"), spouse_itemizing=fact(answer))
    result = evaluate(facts)
    assert result["eligibility"]["in_scope"] is (not expected)
    if expected:
        assert_human_escalation(result, OUT_OF_SCOPE)


def test_extracted_1099r_box_2b_escalates_and_cites_policy():
    extracted = {"doc-1": {"kind": "1099-R", "fields": {"box_2b": fact("yes", "doc-1")}}}
    result = evaluate(single_facts(), extracted=extracted)
    assert result["eligibility"]["in_scope"] is False
    assert_human_escalation(result, FORM_1099R_BOX_2B)
    assert_citation(result, "Form 1099-R Box 2b screening", "3.2")


def test_social_security_document_adds_worksheet_citation():
    extracted = {"doc-ssa": {"kind": "SSA-1099", "fields": {}}}
    result = evaluate(single_facts(), extracted=extracted)
    assert result["handoff_request"]["to"] == "computation"
    assert_citation(result, "Taxable Social Security worksheet", "2.6")


def test_enhanced_senior_deduction_rule_is_cited_when_applicable():
    result = evaluate(single_facts())
    assert_citation(result, "Schedule 1-A enhanced senior deduction", "2.5")


# --- Existing and resolved human escalations ---------------------------------


@pytest.mark.parametrize("condition", [TAX_ADVICE_REQUEST, EXPLOITATION_SIGNS, SOURCE_CONFLICT])
def test_existing_pending_safety_escalation_is_preserved(condition):
    previous = {"pending": True, "condition": condition, "reason": "Raised by Intake", "raised_by": "intake"}
    result = evaluate(single_facts(), escalation=previous)
    assert result["escalation"] == previous
    assert result["handoff_request"]["to"] == "human"
    assert result["handoff_request"]["reason"] == condition


def test_human_continue_prevents_repeating_out_of_scope_escalation():
    result = evaluate(
        single_facts(business_or_rental_income=fact("yes")),
        human_decisions=[{"condition": OUT_OF_SCOPE, "decision": "continue"}],
    )
    assert result["eligibility"]["in_scope"] is False
    assert "escalation" not in result
    assert result["handoff_request"]["to"] == "computation"
