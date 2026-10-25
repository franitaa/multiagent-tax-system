"""Coordinate tax calculations in dependency order."""

from typing import Any

from tax_math import (
    calculate_standard_deduction,
    calculate_senior_deduction,
    calculate_taxable_social_security,
)


def run_computation_agent(
    filing_status: str,
    other_income: float,
    benefits: float,
    tax_exempt_interest: float,
    magi: float,
    qualifying_people: int,
    age_65_or_older: bool = False,
    blind: bool = False,
    spouse_age_65_or_older: bool = False,
    spouse_blind: bool = False,
) -> dict[str, Any]:
    """Calculate key tax amounts and retain provenance for each result."""

    # Step 1: Calculate taxable Social Security (Form 1040 line 6b).
    social_security = calculate_taxable_social_security(
        benefits=benefits,
        other_income=other_income,
        tax_exempt_interest=tax_exempt_interest,
        filing_status=filing_status,
    )

    # Step 2: Calculate AGI after including taxable Social Security.
    agi_value = other_income + social_security["value"]

    agi = {
        "value": round(agi_value, 2),
        "formula": "other_income + taxable_social_security",
        "inputs": {
            "other_income": other_income,
            "line_6b": social_security["value"],
        },
        "source": "Calculated from supplied income and Form 1040 line 6b",
        "tool": "run_computation_agent",
    }

    # Step 3: Calculate the standard deduction.
    standard_deduction = calculate_standard_deduction(
        filing_status=filing_status,
        age_65_or_older=age_65_or_older,
        blind=blind,
        spouse_age_65_or_older=spouse_age_65_or_older,
        spouse_blind=spouse_blind,
    )

    # Step 4: Calculate the enhanced senior deduction.
    senior_deduction = calculate_senior_deduction(
        magi=magi,
        qualifying_people=qualifying_people,
        filing_status=filing_status,
    )

    return {
        "line_6b_taxable_social_security": social_security,
        "agi": agi,
        "standard_deduction": standard_deduction,
        "senior_deduction": senior_deduction,
    }
