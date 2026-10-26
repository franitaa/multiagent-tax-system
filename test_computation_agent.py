"""Tests for the computation agent."""

from computation_agent import run_computation_agent


def test_computation_agent():
    result = run_computation_agent(
        filing_status="single",
        other_income=50000,
        benefits=10000,
        tax_exempt_interest=0,
        magi=50000,
        qualifying_people=0,
    )

    # Verify the expected output sections exist.
    assert "line_6b_taxable_social_security" in result
    assert "agi" in result
    assert "standard_deduction" in result
    assert "senior_deduction" in result

    # Verify line 6b is included in AGI.
    taxable_ss = result["line_6b_taxable_social_security"]["value"]
    assert result["agi"]["value"] == 50000 + taxable_ss

    # Verify provenance is retained for each calculation.
    assert result["line_6b_taxable_social_security"]["tool"] == (
        "calculate_taxable_social_security"
    )
    assert result["standard_deduction"]["tool"] == (
        "calculate_standard_deduction"
    )
    assert result["senior_deduction"]["tool"] == (
        "calculate_senior_deduction"
    )

    print("All computation agent tests passed!")


if __name__ == "__main__":
    test_computation_agent()
