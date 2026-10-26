"""Focused tests for the Eligibility & Rules Agent."""

from src.agents.rules import run


def fact(value, source="test"):
    """
    Helper to create facts in the same format used by SilverFile.
    """
    return {
        "value": value,
        "source": source,
    }


def make_view(facts=None, extracted=None, human_decisions=None):
    """
    Build a minimal scoped view for the Rules agent.
    """
    return {
        "facts": facts or {},
        "extracted": extracted or {},
        "session_summary": {},
        "escalation": {},
        "human_decisions": human_decisions or [],
    }


# ---------------------------------------------------------------------
# 1. Clean eligible taxpayer
# ---------------------------------------------------------------------

def test_single_taxpayer_is_eligible():
    view = make_view(
        facts={
            "age": fact(70),
            "filing_status_claim": fact("single"),
        }
    )

    result = run(view, tools={})

    eligibility = result["eligibility"]

    assert eligibility["eligible_1040sr"] is True
    assert eligibility["filing_status_valid"] is True
    assert eligibility["in_scope"] is True

    assert result["handoff_request"]["to"] == "computation"


# ---------------------------------------------------------------------
# 2. Taxpayer too young
# ---------------------------------------------------------------------

def test_single_taxpayer_not_eligible():
    view = make_view(
        facts={
            "age": fact(60),
            "filing_status_claim": fact("single"),
        }
    )

    result = run(view, tools={})

    eligibility = result["eligibility"]

    assert eligibility["eligible_1040sr"] is False
    assert eligibility["in_scope"] is False

    assert result["escalation"]["pending"] is True
    assert result["handoff_request"]["to"] == "human"


# ---------------------------------------------------------------------
# 3. Exact DOB rule
# ---------------------------------------------------------------------

def test_exact_dob_rule_before_cutoff_is_eligible():
    view = make_view(
        facts={
            "taxpayer_dob": fact("1961-01-01"),
            "filing_status_claim": fact("single"),
        }
    )

    result = run(view, tools={})

    assert (
        result["eligibility"]["eligible_1040sr"]
        is True
    )


def test_exact_dob_rule_on_cutoff_is_not_eligible():
    view = make_view(
        facts={
            "taxpayer_dob": fact("1961-01-02"),
            "filing_status_claim": fact("single"),
        }
    )

    result = run(view, tools={})

    assert (
        result["eligibility"]["eligible_1040sr"]
        is False
    )

    assert (
        result["handoff_request"]["to"]
        == "human"
    )


# ---------------------------------------------------------------------
# 4. MFJ: only one spouse needs to qualify
# ---------------------------------------------------------------------

def test_mfj_spouse_can_make_return_eligible():
    view = make_view(
        facts={
            "age": fact(60),
            "spouse_age": fact(70),
            "filing_status_claim": fact("mfj"),
        }
    )

    result = run(view, tools={})

    eligibility = result["eligibility"]

    assert eligibility["taxpayer_qualifies"] is False
    assert eligibility["spouse_qualifies"] is True
    assert eligibility["eligible_1040sr"] is True

    assert result["handoff_request"]["to"] == "computation"


# ---------------------------------------------------------------------
# 5. Invalid filing status
# ---------------------------------------------------------------------

def test_invalid_filing_status_escalates():
    view = make_view(
        facts={
            "age": fact(70),
            "filing_status_claim": fact("invalid_status"),
        }
    )

    result = run(view, tools={})

    assert (
        result["eligibility"]["filing_status_valid"]
        is False
    )

    assert result["escalation"]["pending"] is True
    assert result["handoff_request"]["to"] == "human"


# ---------------------------------------------------------------------
# 6. Missing information
# ---------------------------------------------------------------------

def test_missing_age_returns_to_intake():
    view = make_view(
        facts={
            "filing_status_claim": fact("single"),
        }
    )

    result = run(view, tools={})

    assert result["handoff_request"]["to"] == "intake"

    assert "Missing required information" in (
        result["handoff_request"]["reason"]
    )


def test_missing_filing_status_returns_to_intake():
    view = make_view(
        facts={
            "age": fact(70),
        }
    )

    result = run(view, tools={})

    assert result["handoff_request"]["to"] == "intake"


# ---------------------------------------------------------------------
# 7. Age/blindness boxes
# ---------------------------------------------------------------------

def test_age_blindness_box_count_single():
    view = make_view(
        facts={
            "age": fact(70),
            "filing_status_claim": fact("single"),
            "taxpayer_blind": fact(True),
        }
    )

    result = run(view, tools={})

    assert (
        result["eligibility"]["age_blindness_boxes"]
        == 2
    )


def test_age_blindness_box_count_mfj():
    view = make_view(
        facts={
            "age": fact(70),
            "spouse_age": fact(70),
            "filing_status_claim": fact("mfj"),
            "taxpayer_blind": fact(True),
            "spouse_blind": fact(True),
        }
    )

    result = run(view, tools={})

    assert (
        result["eligibility"]["age_blindness_boxes"]
        == 4
    )


# ---------------------------------------------------------------------
# 8. Schedule C / self-employment is out of scope
# ---------------------------------------------------------------------

def test_self_employment_is_out_of_scope():
    view = make_view(
        facts={
            "age": fact(70),
            "filing_status_claim": fact("single"),
            "has_self_employment_income": fact(True),
        }
    )

    result = run(view, tools={})

    assert result["eligibility"]["in_scope"] is False

    assert result["escalation"]["pending"] is True

    assert (
        result["handoff_request"]["to"]
        == "human"
    )

    assert any(
        "Schedule C" in reason
        for reason in result["eligibility"][
            "out_of_scope_reasons"
        ]
    )


# ---------------------------------------------------------------------
# 9. Rental income is out of scope
# ---------------------------------------------------------------------

def test_rental_income_is_out_of_scope():
    view = make_view(
        facts={
            "age": fact(70),
            "filing_status_claim": fact("single"),
            "has_rental_income": fact(True),
        }
    )

    result = run(view, tools={})

    assert result["eligibility"]["in_scope"] is False

    assert result["handoff_request"]["to"] == "human"


# ---------------------------------------------------------------------
# 10. Digital assets are out of scope
# ---------------------------------------------------------------------

def test_digital_assets_are_out_of_scope():
    view = make_view(
        facts={
            "age": fact(70),
            "filing_status_claim": fact("single"),
            "has_digital_assets": fact(True),
        }
    )

    result = run(view, tools={})

    assert result["eligibility"]["in_scope"] is False

    assert result["handoff_request"]["to"] == "human"


# ---------------------------------------------------------------------
# 11. 1099-R Box 2b escalation from facts
# ---------------------------------------------------------------------

def test_1099r_box_2b_from_facts_escalates():
    view = make_view(
        facts={
            "age": fact(70),
            "filing_status_claim": fact("single"),
            "has_1099r_taxable_amount_not_determined":
                fact(True),
        }
    )

    result = run(view, tools={})

    assert result["eligibility"]["in_scope"] is False

    assert result["escalation"]["pending"] is True

    assert (
        result["handoff_request"]["to"]
        == "human"
    )


# ---------------------------------------------------------------------
# 12. 1099-R Box 2b escalation from extracted document
# ---------------------------------------------------------------------

def test_1099r_box_2b_from_extracted_document():
    extracted = {
        "doc-1": {
            "kind": "1099-R",

            "fields": {
                "box_2b": {
                    "value": True,
                    "source": "doc-1",
                }
            },
        }
    }

    view = make_view(
        facts={
            "age": fact(70),
            "filing_status_claim": fact("single"),
        },
        extracted=extracted,
    )

    result = run(view, tools={})

    assert result["eligibility"]["in_scope"] is False

    assert result["escalation"]["pending"] is True

    assert (
        result["handoff_request"]["to"]
        == "human"
    )


# ---------------------------------------------------------------------
# 13. Filing-status ambiguity
# ---------------------------------------------------------------------

def test_filing_status_ambiguity_escalates():
    view = make_view(
        facts={
            "age": fact(70),
            "filing_status_claim": fact("single"),
            "filing_status_ambiguous": fact(True),
        }
    )

    result = run(view, tools={})

    assert result["escalation"]["pending"] is True

    assert (
        result["handoff_request"]["to"]
        == "human"
    )


# ---------------------------------------------------------------------
# 14. Spouse death during tax year
# ---------------------------------------------------------------------

def test_spouse_death_triggers_filing_status_review():
    view = make_view(
        facts={
            "age": fact(70),
            "filing_status_claim": fact("mfj"),
            "spouse_age": fact(70),
            "spouse_died_during_tax_year": fact(True),
        }
    )

    result = run(view, tools={})

    assert result["escalation"]["pending"] is True

    assert result["handoff_request"]["to"] == "human"


# ---------------------------------------------------------------------
# 15. Source conflict
# ---------------------------------------------------------------------

def test_document_user_conflict_escalates():
    view = make_view(
        facts={
            "age": fact(70),
            "filing_status_claim": fact("single"),
            "document_user_conflict": fact(True),
        }
    )

    result = run(view, tools={})

    assert result["escalation"]["pending"] is True

    assert (
        result["handoff_request"]["to"]
        == "human"
    )


# ---------------------------------------------------------------------
# 16. Tax advice request
# ---------------------------------------------------------------------

def test_tax_advice_request_escalates():
    view = make_view(
        facts={
            "age": fact(70),
            "filing_status_claim": fact("single"),
            "tax_advice_requested": fact(True),
        }
    )

    result = run(view, tools={})

    assert result["escalation"]["pending"] is True

    assert result["handoff_request"]["to"] == "human"


# ---------------------------------------------------------------------
# 17. Financial exploitation
# ---------------------------------------------------------------------

def test_exploitation_flag_escalates():
    view = make_view(
        facts={
            "age": fact(70),
            "filing_status_claim": fact("single"),
            "financial_exploitation_flag": fact(True),
        }
    )

    result = run(view, tools={})

    assert result["escalation"]["pending"] is True

    assert result["handoff_request"]["to"] == "human"


# ---------------------------------------------------------------------
# 18. Standard deduction exception
# ---------------------------------------------------------------------

def test_dependent_standard_deduction_exception():
    view = make_view(
        facts={
            "age": fact(70),
            "filing_status_claim": fact("single"),
            "taxpayer_can_be_claimed_as_dependent":
                fact(True),
        }
    )

    result = run(view, tools={})

    assert result["eligibility"]["in_scope"] is False
    assert result["escalation"]["pending"] is True
    assert result["handoff_request"]["to"] == "human"


# ---------------------------------------------------------------------
# 19. Senior deduction rule applicability
# ---------------------------------------------------------------------

def test_senior_deduction_rule_is_identified():
    view = make_view(
        facts={
            "age": fact(70),
            "filing_status_claim": fact("single"),
        }
    )

    result = run(view, tools={})

    assert (
        "Schedule 1-A enhanced senior deduction"
        in result["eligibility"]["applicable_rules"]
    )


# ---------------------------------------------------------------------
# 20. Social Security rule dependency
# ---------------------------------------------------------------------

def test_ssa1099_adds_social_security_rule():
    extracted = {
        "doc-ssa": {
            "kind": "SSA-1099",
            "fields": {},
        }
    }

    view = make_view(
        facts={
            "age": fact(70),
            "filing_status_claim": fact("single"),
        },
        extracted=extracted,
    )

    result = run(view, tools={})

    assert (
        "Taxable Social Security worksheet"
        in result["eligibility"]["applicable_rules"]
    )


# ---------------------------------------------------------------------
# 21. Resolved condition should not be raised again
# ---------------------------------------------------------------------

def test_resolved_out_of_scope_condition_not_repeated():
    view = make_view(
        facts={
            "age": fact(70),
            "filing_status_claim": fact("single"),
            "has_self_employment_income": fact(True),
        },

        human_decisions=[
            {
                "condition": "OUT_OF_SCOPE",
                "decision": "continue",
            }
        ],
    )

    result = run(view, tools={})

    # The same OUT_OF_SCOPE escalation should not be
    # raised again after human resolution.
    assert "escalation" not in result