"""Assignment 7: Eligibility & Rules Agent tests for 2025 Form 1040-SR.

Based on the assignment specification:
  - section 3.2: 1040-SR age cutoff, age/blindness boxes, Schedule 1-A,
                 taxable Social Security applicability;
  - section 3.3: supported tax scope and out-of-scope escalation;
  - section 4:   Rules ownership, evidence/citations, human review.

The tests check ONLY responsibilities owned by the Rules Agent. Monetary
arithmetic, W-2 image extraction, draft-form generation, and end-to-end LangGraph
interrupt/resume are owned by other components and need separate tests.

IMPORTANT: This is a Rules UNIT test suite. It checks actual return values of
src.agents.rules.run(), including pending ANSWER_UNCERTAIN escalation and
human-supplied fact resolution. It does NOT simulate the real LangGraph
interrupt/resume mechanism, which needs a separate orchestrator test.

The 1099-NEC test is marked xfail(strict=True) because the supplied
rules(7).py does not screen an extracted 1099-NEC document unless an Intake
scope-screening fact identifies it. Remove xfail once that gap is fixed.

Run from the repository root:
    python -m pytest tests/test_rules.py -v
"""

from pathlib import Path
import re

import pytest

from src.agents.rules import run
from src import state as S


POLICY_PATH = Path(__file__).resolve().parents[1] / "docs" / "policy.md"
BLINDNESS_CONDITION = S.ANSWER_UNCERTAIN


def fact(value, source="user"):
    """Shared Intake -> Rules fact-record shape."""
    return {"value": value, "source": source}


def single_facts(**overrides):
    records = {
        "taxpayer_birth_date": fact("1950-05-10"),
        "married_dec31": fact("no"),
        "household_situation": fact("single"),
        "taxpayer_blind": fact("no"),
        "us_resident_all_year": fact("yes"),
        "can_be_claimed_as_dependent": fact("no"),
    }
    records.update(overrides)
    return records


def joint_facts(**overrides):
    records = {
        "taxpayer_birth_date": fact("1950-05-10"),
        "spouse_birth_date": fact("1952-08-20"),
        "married_dec31": fact("yes"),
        "file_jointly": fact("yes"),
        "taxpayer_blind": fact("no"),
        "spouse_blind": fact("no"),
        "spouse_can_be_claimed": fact("no"),
        "us_resident_all_year": fact("yes"),
    }
    records.update(overrides)
    return records


def evaluate(facts=None, *, extracted=None, escalation=None, human_decisions=None, tools=None):
    view = {
        "facts": single_facts() if facts is None else facts,
        "extracted": {} if extracted is None else extracted,
        "session_summary": "",
        "escalation": escalation,
        "human_decisions": [] if human_decisions is None else human_decisions,
    }
    return run(view, {} if tools is None else tools)


def require_rule(result, rule_name, section):
    expected = {"rule": rule_name, "citation": f"policy.md §{section}"}
    assert expected in result["eligibility"]["rule_citations"], (
        f"Missing cited rule: {expected}"
    )


def require_escalation(result, condition):
    assert result["handoff_request"]["to"] == "human"
    assert result.get("escalation", {}).get("pending") is True, (
        "A handoff_request alone does not interrupt the orchestrator"
    )
    assert result["escalation"]["condition"] == condition
    assert result["escalation"]["raised_by"] == "rules"


# 1. Shared Rules output contract --------------------------------------------


def test_clean_single_returns_valid_eligibility_and_computation_handoff():
    result = evaluate()
    e = result["eligibility"]
    assert e["eligible_1040sr"] is True
    assert e["taxpayer_qualifies"] is True
    assert e["filing_status"] == "single"
    assert e["filing_status_valid"] is True
    assert e["in_scope"] is True
    assert e["age_blindness_boxes"] == 1
    assert e["out_of_scope_reasons"] == []
    assert result["handoff_request"]["to"] == "computation"


def test_required_fields_and_boolean_scope_are_present():
    for facts in (single_facts(), joint_facts(), single_facts(taxpayer_blind=fact("not_sure"))):
        e = evaluate(facts)["eligibility"]
        assert {
            "eligible_1040sr", "taxpayer_qualifies", "spouse_qualifies",
            "filing_status", "filing_status_valid", "in_scope",
            "age_blindness_boxes", "out_of_scope_reasons", "rule_citations",
        } <= e.keys()
        assert isinstance(e["filing_status"], str)
        assert isinstance(e["in_scope"], bool)
        assert isinstance(e["age_blindness_boxes"], int)


def test_rules_emits_no_computation_or_filing_update():
    result = evaluate()
    assert "computed" not in result
    assert "documents" not in result
    assert "form_1040sr" not in result


def test_rules_does_not_call_arithmetic_tools():
    class NoArithmeticTools:
        def call(self, *args, **kwargs):
            raise AssertionError("Rules must not call computation tools")

    assert evaluate(tools=NoArithmeticTools())["eligibility"]["in_scope"] is True


# 2. Form 1040-SR eligibility (Assignment 7 section 3.2 rule 1) -------------


@pytest.mark.parametrize(
    ("dob", "eligible"),
    [("1950-05-10", True), ("1961-01-01", True),
     ("1961-01-02", False), ("1965-06-15", False)],
)
def test_taxpayer_2025_birth_date_boundary(dob, eligible):
    result = evaluate(single_facts(taxpayer_birth_date=fact(dob)))
    assert result["eligibility"]["eligible_1040sr"] is eligible
    require_rule(result, "1040-SR eligibility", "2.1")
    if not eligible:
        assert result["eligibility"]["in_scope"] is False
        require_escalation(result, S.OUT_OF_SCOPE)


def test_high_income_does_not_disqualify_an_eligible_senior():
    # Assignment 7 section 3.2 states there is no income restriction.
    result = evaluate(extracted={
        "doc-w2": {"kind": "W-2", "fields": {"box_1": {"value": 900000}}}
    })
    assert result["eligibility"]["eligible_1040sr"] is True
    assert result["eligibility"]["in_scope"] is True


def test_joint_return_eligible_when_only_spouse_is_senior():
    result = evaluate(joint_facts(
        taxpayer_birth_date=fact("1965-01-01"),
        spouse_birth_date=fact("1950-01-01"),
    ))
    e = result["eligibility"]
    assert e["taxpayer_qualifies"] is False
    assert e["spouse_qualifies"] is True
    assert e["eligible_1040sr"] is True
    assert e["age_blindness_boxes"] == 1
    assert result["handoff_request"]["to"] == "computation"


def test_joint_return_ineligible_when_both_under_65():
    result = evaluate(joint_facts(
        taxpayer_birth_date=fact("1965-01-01"),
        spouse_birth_date=fact("1966-01-01"),
    ))
    assert result["eligibility"]["eligible_1040sr"] is False
    assert result["eligibility"]["age_blindness_boxes"] == 0
    require_escalation(result, S.OUT_OF_SCOPE)


def test_nonjoint_return_does_not_use_spouse_age_to_qualify():
    result = evaluate(single_facts(
        taxpayer_birth_date=fact("1965-01-01"),
        spouse_birth_date=fact("1948-01-01"),
    ))
    assert result["eligibility"]["eligible_1040sr"] is False
    require_escalation(result, S.OUT_OF_SCOPE)


@pytest.mark.parametrize("dob", [None, "not_sure", "not-a-date"])
def test_missing_or_uncertain_taxpayer_dob_is_not_guessed(dob):
    facts = single_facts()
    if dob is None:
        del facts["taxpayer_birth_date"]
    else:
        facts["taxpayer_birth_date"] = fact(dob)
    result = evaluate(facts)
    assert result["eligibility"]["eligible_1040sr"] is None
    assert result["handoff_request"]["to"] == "intake"


def test_missing_joint_spouse_dob_does_not_erase_known_taxpayer_eligibility():
    facts = joint_facts()
    del facts["spouse_birth_date"]
    result = evaluate(facts)
    assert result["eligibility"]["eligible_1040sr"] is True
    assert result["eligibility"]["age_blindness_boxes"] == 1


# 3. Filing-status validation (five statuses) -------------------------------


@pytest.mark.parametrize(
    ("full_name", "expected"),
    [("single", "single"), ("married_filing_jointly", "married_filing_jointly"),
     ("married_filing_separately", "married_filing_separately"),
     ("head_of_household", "head_of_household"),
     ("qualifying_surviving_spouse", "qualifying_surviving_spouse")],
)
def test_all_five_human_approved_filing_statuses(full_name, expected):
    facts = single_facts(filing_status=fact(full_name, "human:FILING_STATUS_AMBIGUITY"))
    result = evaluate(facts)
    e = result["eligibility"]
    assert e["filing_status"] == expected
    assert e["filing_status_valid"] is True
    require_rule(result, "Filing status validation", "2.2")


def test_joint_marriage_answers_derive_mfj():
    assert evaluate(joint_facts())["eligibility"]["filing_status"] == "married_filing_jointly"


def test_married_filing_separately_derived_from_intake_answers():
    facts = joint_facts(file_jointly=fact("no"), spouse_itemizing=fact("no"))
    result = evaluate(facts)
    assert result["eligibility"]["filing_status"] == "married_filing_separately"
    assert result["handoff_request"]["to"] == "computation"


@pytest.mark.parametrize("overrides", [
    {"married_dec31": fact("no"), "household_situation": fact("caring_for_someone")},
    {"married_dec31": fact("no"), "household_situation": fact("widowed")},
])
def test_ambiguous_filing_status_escalates_not_guessed(overrides):
    result = evaluate(single_facts(**overrides))
    assert result["eligibility"]["filing_status"] == "undetermined"
    assert result["eligibility"]["filing_status_valid"] is False
    require_escalation(result, S.FILING_STATUS_AMBIGUITY)


def test_untrusted_user_claim_does_not_override_validated_filing_status():
    result = evaluate(single_facts(filing_status=fact("head_of_household", "user")))
    assert result["eligibility"]["filing_status"] == "single"


def test_human_status_override_is_honored_after_ambiguity():
    facts = single_facts(
        married_dec31=fact("not_sure"),
        filing_status=fact("single", "human:FILING_STATUS_AMBIGUITY"),
    )
    result = evaluate(facts, human_decisions=[{
        "condition": S.FILING_STATUS_AMBIGUITY, "decision": "continue"
    }])
    assert result["eligibility"]["filing_status"] == "single"
    assert result["handoff_request"]["to"] == "computation"
    assert result.get("escalation") is None


# 4. Form 1040-SR line 12d: age and blindness boxes ------------------------


@pytest.mark.parametrize(
    ("blind", "boxes", "destination"),
    [("no", 1, "computation"), ("yes", 2, "computation"),
     ("not_sure", 1, "human")],
)
def test_75_year_old_preserves_age_box_for_all_blindness_answers(blind, boxes, destination):
    result = evaluate(single_facts(taxpayer_blind=fact(blind)))
    assert result["eligibility"]["age_blindness_boxes"] == boxes
    assert result["handoff_request"]["to"] == destination
    require_rule(result, "Standard deduction age/blindness rule", "2.3")
    if blind == "not_sure":
        require_rule(result, "Uncertain blindness: human review", "3.3")


@pytest.mark.parametrize(
    ("spouse_blind", "boxes", "destination"),
    [("no", 2, "computation"), ("yes", 3, "computation"),
     ("not_sure", 2, "human")],
)
def test_joint_ages_preserved_when_spouse_blindness_varies(spouse_blind, boxes, destination):
    result = evaluate(joint_facts(spouse_blind=fact(spouse_blind)))
    assert result["eligibility"]["age_blindness_boxes"] == boxes
    assert result["handoff_request"]["to"] == destination
    if spouse_blind == "not_sure":
        require_rule(result, "Uncertain blindness: human review", "3.3")


def test_joint_four_boxes_when_both_seniors_and_confirmed_blind():
    result = evaluate(joint_facts(taxpayer_blind=fact("yes"), spouse_blind=fact("yes")))
    assert result["eligibility"]["age_blindness_boxes"] == 4


def test_unknown_spouse_blindness_preserves_confirmed_taxpayer_blindness():
    result = evaluate(joint_facts(taxpayer_blind=fact("yes"), spouse_blind=fact("not_sure")))
    assert result["eligibility"]["age_blindness_boxes"] == 3
    assert result["handoff_request"]["to"] == "human"


def test_irrelevant_spouse_blindness_is_ignored_for_single_filer():
    result = evaluate(single_facts(spouse_blind=fact("not_sure")))
    assert result["eligibility"]["age_blindness_boxes"] == 1
    assert result["handoff_request"]["to"] == "computation"


@pytest.mark.parametrize("bad_answer", ["maybe", "unknown", "", 123])
def test_invalid_blindness_answer_not_silently_treated_as_no(bad_answer):
    result = evaluate(single_facts(taxpayer_blind=fact(bad_answer)))
    assert result["eligibility"]["age_blindness_boxes"] == 1
    assert result["handoff_request"]["to"] == "intake"


def test_human_confirmed_blindness_can_be_used_after_resolution():
    facts = single_facts(taxpayer_blind=fact("yes", "human:ANSWER_UNCERTAIN"))
    result = evaluate(facts)
    assert result["eligibility"]["age_blindness_boxes"] == 2
    assert result["handoff_request"]["to"] == "computation"


def test_unknown_taxpayer_blindness_creates_real_pending_escalation():
    result = evaluate(single_facts(taxpayer_blind=fact("not_sure")))
    assert result["eligibility"]["age_blindness_boxes"] == 1
    require_escalation(result, S.ANSWER_UNCERTAIN)
    assert "taxpayer_blind" in result["escalation"]["reason"]


def test_unknown_spouse_blindness_creates_real_pending_escalation():
    result = evaluate(joint_facts(spouse_blind=fact("not_sure")))
    assert result["eligibility"]["age_blindness_boxes"] == 2
    require_escalation(result, S.ANSWER_UNCERTAIN)
    assert "spouse_blind" in result["escalation"]["reason"]


# 5. Which schedules / worksheets apply (Rules flags, Computation calculates)


def test_standard_deduction_chart_is_cited_for_clean_case():
    result = evaluate()
    require_rule(result, "Standard deduction chart applicability", "2.4")


def test_enhanced_senior_deduction_is_separate_from_age_boxes():
    result = evaluate()
    require_rule(result, "Standard deduction age/blindness rule", "2.3")
    require_rule(result, "Schedule 1-A enhanced senior deduction", "2.5")
    assert "computed" not in result  # no $6,000 calculation by Rules


def test_married_filing_separately_does_not_claim_schedule_1a_senior_rule():
    result = evaluate(joint_facts(file_jointly=fact("no"), spouse_itemizing=fact("no")))
    rules = {record["rule"] for record in result["eligibility"]["rule_citations"]}
    assert "Schedule 1-A enhanced senior deduction" not in rules


@pytest.mark.parametrize("kind", ["SSA-1099", "ssa1099"])
def test_social_security_document_flags_taxable_benefits_worksheet(kind):
    result = evaluate(extracted={"doc-ssa": {"kind": kind, "fields": {}}})
    require_rule(result, "Taxable Social Security worksheet", "2.6")
    assert result["handoff_request"]["to"] == "computation"


def test_social_security_worksheet_not_flagged_without_ssa_1099():
    result = evaluate(extracted={"doc-w2": {"kind": "W-2", "fields": {}}})
    names = {pair["rule"] for pair in result["eligibility"]["rule_citations"]}
    assert "Taxable Social Security worksheet" not in names


# 6. Supported scope / out-of-scope conditions (section 3.3) --------------


@pytest.mark.parametrize("name", [
    "has_other_tax_forms", "sold_stocks_or_property",
    "business_or_rental_income", "foreign_income_or_accounts",
    "digital_assets", "can_be_claimed_as_dependent",
])
def test_unsupported_activity_escalates_and_cites_scope(name):
    result = evaluate(single_facts(**{name: fact("yes")}))
    assert result["eligibility"]["in_scope"] is False
    require_escalation(result, S.OUT_OF_SCOPE)
    require_rule(result, "Out-of-scope screening", "3.1")


def test_non_full_year_residency_escalates():
    result = evaluate(single_facts(us_resident_all_year=fact("no")))
    assert result["eligibility"]["in_scope"] is False
    require_escalation(result, S.OUT_OF_SCOPE)


def test_not_sure_scope_answer_is_not_assumed_safe():
    # Current Rules treats uncertainty as out-of-scope, not a clarify-once loop.
    # If the team adopts clarify-once, this assertion must be updated.
    result = evaluate(single_facts(digital_assets=fact("not_sure")))
    assert result["handoff_request"]["to"] == "human"
    assert result["eligibility"]["in_scope"] is False
    require_escalation(result, S.OUT_OF_SCOPE)


@pytest.mark.parametrize("answer", ["yes", "not_sure"])
def test_spouse_eligible_as_dependent_is_escalated_for_joint_return(answer):
    result = evaluate(joint_facts(spouse_can_be_claimed=fact(answer)))
    assert result["eligibility"]["in_scope"] is False
    require_escalation(result, S.OUT_OF_SCOPE)


@pytest.mark.parametrize("answer", ["yes", "not_sure"])
def test_mfs_spouse_itemizes_or_uncertain_escalates(answer):
    result = evaluate(joint_facts(file_jointly=fact("no"), spouse_itemizing=fact(answer)))
    assert result["eligibility"]["in_scope"] is False
    require_escalation(result, S.OUT_OF_SCOPE)


@pytest.mark.parametrize("kind", ["W-2", "1099-INT", "1099-DIV", "1099-R", "SSA-1099"])
def test_supported_document_types_not_rejected_by_kind_alone(kind):
    result = evaluate(extracted={"doc-1": {"kind": kind, "fields": {}}})
    assert result["eligibility"]["in_scope"] is True
    assert result["handoff_request"]["to"] == "computation"


@pytest.mark.parametrize("box_2b", [True, "yes"])
def test_1099r_taxable_amount_not_determined_creates_escalation(box_2b):
    extracted = {
        "1099r-doc": {
            "kind": "1099-R",
            "fields": {"box_2b": {"value": box_2b, "source": "1099r-doc"}},
        },
    }
    result = evaluate(extracted=extracted)
    assert result["eligibility"]["in_scope"] is False
    require_escalation(result, S.FORM_1099R_BOX_2B)
    require_rule(result, "Form 1099-R Box 2b screening", "3.2")

def test_extracted_1099nec_must_not_pass_supported_scope_screening():
    # Assignment 7 section 3.3 excludes 1099-NEC nonemployee compensation.
    # Even if Intake missed it, the extracted document should not silently pass.
    result = evaluate(extracted={
        "doc-nec": {"kind": "1099-NEC", "fields": {"box_1": {"value": 5000}}}
    })
    assert result["eligibility"]["in_scope"] is False
    require_escalation(result, S.OUT_OF_SCOPE)


def test_unchecked_1099r_box_2b_does_not_escalate():
    result = evaluate(extracted={
        "1099r-doc": {"kind": "1099-R", "fields": {"box_2b": {"value": "no"}}},
    })
    assert result["eligibility"]["in_scope"] is True
    assert result["handoff_request"]["to"] == "computation"


# 7. Citation grounding in the provided reference corpus --------------------


def test_canonical_paired_citation_schema_has_no_legacy_fields():
    e = evaluate()["eligibility"]
    assert "applicable_rules" not in e
    assert "citations" not in e
    pairs = e["rule_citations"]
    assert pairs
    assert all(isinstance(pair, dict) and set(pair) == {"rule", "citation"} for pair in pairs)
    assert len({pair["rule"] for pair in pairs}) == len(pairs)
    require_rule({"eligibility": e}, "1040-SR eligibility", "2.1")
    require_rule({"eligibility": e}, "Filing status validation", "2.2")


def test_all_cited_sections_exist_in_data_policy_md():
    assert POLICY_PATH.is_file(), f"Missing Rules reference corpus at {POLICY_PATH}"
    text = POLICY_PATH.read_text(encoding="utf-8")
    sections = set(re.findall(r"^##\s+(\d+\.\d+)\b", text, flags=re.M))
    assert sections, "Expected numbered ## 2.1, ## 2.2, ... headings in policy.md"
    scenarios = [
        evaluate(),
        evaluate(single_facts(taxpayer_blind=fact("not_sure"))),
        evaluate(single_facts(digital_assets=fact("yes"))),
        evaluate(extracted={
            "doc": {"kind": "1099-R", "fields": {"box_2b": {"value": "yes"}}}
        }),
        evaluate(extracted={"doc": {"kind": "SSA-1099", "fields": {}}}),
    ]
    for result in scenarios:
        for pair in result["eligibility"]["rule_citations"]:
            match = re.fullmatch(r"policy\.md §(\d+\.\d+)", pair["citation"])
            assert match, f"Invalid policy citation: {pair}"
            assert match.group(1) in sections, f"Unknown policy section: {pair}"


# 8. Cross-agent safety / escalation preservation ---------------------------


@pytest.mark.parametrize("condition", [
    S.SOURCE_CONFLICT, S.TAX_ADVICE_REQUEST, S.EXPLOITATION_SIGNS,
    S.FILING_STATUS_AMBIGUITY,
])
def test_existing_pending_safety_escalation_is_not_overwritten(condition):
    pending = {
        "pending": True, "condition": condition,
        "reason": "Needs volunteer review", "raised_by": "intake",
    }
    result = evaluate(escalation=pending)
    assert result["escalation"] == pending
    assert result["handoff_request"]["to"] == "human"


# Note: A real graph test must invoke build_graph(...), assert __interrupt__,
# assert status == awaiting_human, then resume via Command(resume={...}).
# This cannot be established by testing src.agents.rules.run() alone.

# 9. PR #21: ANSWER_UNCERTAIN for relevant filing-status facts -----------


@pytest.mark.parametrize(
    ("overrides", "uncertain_fact"),
    [
        ({"married_dec31": fact("not_sure")}, "married_dec31"),
        ({"married_dec31": fact("yes"), "file_jointly": fact("not_sure")}, "file_jointly"),
        ({"married_dec31": fact("no"), "household_situation": fact("not_sure")},
         "household_situation"),
    ],
)
def test_relevant_not_sure_filing_answers_raise_answer_uncertain(overrides, uncertain_fact):
    result = evaluate(single_facts(**overrides))
    assert result["eligibility"]["filing_status"] == "undetermined"
    assert result["eligibility"]["filing_status_valid"] is False
    assert isinstance(result["eligibility"]["in_scope"], bool)
    require_escalation(result, S.ANSWER_UNCERTAIN)
    assert uncertain_fact in result["escalation"]["reason"]
    require_rule(result, "Filing status validation", "2.2")


@pytest.mark.parametrize(
    ("overrides", "expected_long_status"),
    [
        ({"file_jointly": fact("not_sure")}, "single"),
        ({"spouse_blind": fact("not_sure")}, "single"),
        ({"married_dec31": fact("yes"), "file_jointly": fact("yes"),
          "spouse_birth_date": fact("1952-08-20"),
          "household_situation": fact("not_sure")}, "married_filing_jointly"),
        ({"married_dec31": fact("yes"), "file_jointly": fact("no"),
          "spouse_birth_date": fact("1952-08-20"),
          "household_situation": fact("not_sure"),
          "spouse_itemizing": fact("no")}, "married_filing_separately"),
    ],
)
def test_irrelevant_not_sure_answers_do_not_block_valid_filing_status(
    overrides, expected_long_status
):
    result = evaluate(single_facts(**overrides))
    assert result["eligibility"]["filing_status"] == expected_long_status
    assert result["handoff_request"]["to"] == "computation"
    assert not result.get("escalation", {}).get("pending", False)


@pytest.mark.parametrize(
    ("overrides", "resolved_name", "resolved_value", "expected_status"),
    [
        ({"married_dec31": fact("not_sure")}, "married_dec31", "no", "single"),
        ({"married_dec31": fact("yes"), "file_jointly": fact("not_sure"),
          "spouse_birth_date": fact("1952-08-20")},
         "file_jointly", "yes", "married_filing_jointly"),
        ({"married_dec31": fact("yes"), "file_jointly": fact("not_sure"),
          "spouse_birth_date": fact("1952-08-20"), "spouse_itemizing": fact("no")},
         "file_jointly", "no", "married_filing_separately"),
        ({"household_situation": fact("not_sure")},
         "household_situation", "single", "single"),
    ],
)
def test_volunteer_resolution_of_filing_answers_allows_computation(
    overrides, resolved_name, resolved_value, expected_status
):
    facts = single_facts(**overrides)
    first = evaluate(facts)
    require_escalation(first, S.ANSWER_UNCERTAIN)
    facts[resolved_name] = fact(resolved_value, "human:ANSWER_UNCERTAIN")
    resumed = evaluate(facts, human_decisions=[{
        "condition": S.ANSWER_UNCERTAIN,
        "decision": "continue",
        "note": "Taxpayer confirmed the answer with volunteer",
    }])
    assert resumed["eligibility"]["filing_status"] == expected_status
    assert resumed["eligibility"]["filing_status_valid"] is True
    assert resumed["handoff_request"]["to"] == "computation"
    assert not resumed.get("escalation", {}).get("pending", False)


@pytest.mark.parametrize("unknown_name", ["married_dec31", "file_jointly", "household_situation"])
def test_continue_without_corrected_filing_answer_does_not_bypass_escalation(unknown_name):
    overrides = {"married_dec31": fact("no"), "household_situation": fact("single")}
    if unknown_name == "married_dec31":
        overrides["married_dec31"] = fact("not_sure")
    elif unknown_name == "file_jointly":
        overrides.update(married_dec31=fact("yes"), file_jointly=fact("not_sure"))
    else:
        overrides["household_situation"] = fact("not_sure")
    result = evaluate(single_facts(**overrides), human_decisions=[{
        "condition": S.ANSWER_UNCERTAIN, "decision": "continue",
        "note": "Volunteer did not provide a resolved answer",
    }])
    require_escalation(result, S.ANSWER_UNCERTAIN)
    assert unknown_name in result["escalation"]["reason"]


def test_filing_status_ambiguity_remains_distinct_from_answer_uncertain():
    result = evaluate(single_facts(household_situation=fact("caring_for_someone")))
    require_escalation(result, S.FILING_STATUS_AMBIGUITY)
    assert result["escalation"]["condition"] != S.ANSWER_UNCERTAIN


# 10. PR #21: blindness resolution, known boxes and citation evidence ------


@pytest.mark.parametrize(("corrected", "boxes"), [("yes", 2), ("no", 1)])
def test_human_resolves_unknown_taxpayer_blindness_and_recalculates(corrected, boxes):
    facts = single_facts(taxpayer_blind=fact("not_sure"))
    before = evaluate(facts)
    assert before["eligibility"]["age_blindness_boxes"] == 1
    require_escalation(before, S.ANSWER_UNCERTAIN)
    facts["taxpayer_blind"] = fact(corrected, "human:ANSWER_UNCERTAIN")
    after = evaluate(facts, human_decisions=[{
        "condition": S.ANSWER_UNCERTAIN,
        "decision": "continue",
        "note": "Blindness answer confirmed",
    }])
    assert after["eligibility"]["age_blindness_boxes"] == boxes
    assert after["handoff_request"]["to"] == "computation"
    assert not after.get("escalation", {}).get("pending", False)


@pytest.mark.parametrize(("corrected", "boxes"), [("yes", 3), ("no", 2)])
def test_human_resolves_unknown_spouse_blindness_and_recalculates(corrected, boxes):
    facts = joint_facts(spouse_blind=fact("not_sure"))
    before = evaluate(facts)
    assert before["eligibility"]["age_blindness_boxes"] == 2
    require_escalation(before, S.ANSWER_UNCERTAIN)
    facts["spouse_blind"] = fact(corrected, "human:ANSWER_UNCERTAIN")
    after = evaluate(facts, human_decisions=[{
        "condition": S.ANSWER_UNCERTAIN, "decision": "continue",
        "note": "Spouse confirmed blindness status",
    }])
    assert after["eligibility"]["age_blindness_boxes"] == boxes
    assert after["handoff_request"]["to"] == "computation"


@pytest.mark.parametrize("unknown_fact", ["taxpayer_blind", "spouse_blind"])
def test_continue_without_valid_blindness_answer_still_requires_human(unknown_fact):
    facts = (single_facts(taxpayer_blind=fact("not_sure"))
             if unknown_fact == "taxpayer_blind"
             else joint_facts(spouse_blind=fact("not_sure")))
    result = evaluate(facts, human_decisions=[{
        "condition": S.ANSWER_UNCERTAIN, "decision": "continue"
    }])
    require_escalation(result, S.ANSWER_UNCERTAIN)
    assert unknown_fact in result["escalation"]["reason"]


def test_both_unknown_blindness_answers_do_not_count_unconfirmed_boxes():
    result = evaluate(joint_facts(taxpayer_blind=fact("not_sure"),
                                  spouse_blind=fact("not_sure")))
    assert result["eligibility"]["age_blindness_boxes"] == 2
    require_escalation(result, S.ANSWER_UNCERTAIN)
    assert "taxpayer_blind" in result["escalation"]["reason"]


def test_answer_uncertain_is_not_automatically_classified_out_of_scope():
    result = evaluate(single_facts(taxpayer_blind=fact("not_sure")))
    assert result["eligibility"]["in_scope"] is True
    assert result["eligibility"]["out_of_scope_reasons"] == []
    require_escalation(result, S.ANSWER_UNCERTAIN)


# 11. Long filing status and human override compatibility -----------------


@pytest.mark.parametrize("status", [
    "single", "married_filing_jointly", "married_filing_separately",
    "head_of_household", "qualifying_surviving_spouse",
])
def test_long_filing_status_output_after_human_override(status):
    result = evaluate(single_facts(filing_status=fact(
        status, "human:FILING_STATUS_AMBIGUITY"
    )))
    assert result["eligibility"]["filing_status"] == status
    assert result["eligibility"]["filing_status_valid"] is True


@pytest.mark.parametrize(("raw_married", "raw_jointly", "expected"), [
    (" YES ", " YES ", "married_filing_jointly"),
    ("Yes", "No", "married_filing_separately"),
])
def test_normalized_marriage_answers_preserve_long_status_output(
    raw_married, raw_jointly, expected
):
    result = evaluate(joint_facts(
        married_dec31=fact(raw_married), file_jointly=fact(raw_jointly),
        spouse_itemizing=fact("no"),
    ))
    assert result["eligibility"]["filing_status"] == expected
    assert result["handoff_request"]["to"] == "computation"


def test_returned_filing_status_is_never_an_internal_short_code():
    for facts in [single_facts(), joint_facts(),
                  joint_facts(file_jointly=fact("no"), spouse_itemizing=fact("no"))]:
        status = evaluate(facts)["eligibility"]["filing_status"]
        assert status not in {"mfj", "mfs", "hoh", "qss"}
        assert status in {
            "single", "married_filing_jointly", "married_filing_separately",
            "head_of_household", "qualifying_surviving_spouse",
        }


def test_previous_pending_answer_uncertain_is_preserved_for_human():
    pending = {
        "pending": True, "condition": S.ANSWER_UNCERTAIN,
        "reason": "taxpayer_blind is not_sure", "raised_by": "intake",
    }
    result = evaluate(single_facts(), escalation=pending)
    assert result["escalation"] == pending
    assert result["handoff_request"]["to"] == "human"
