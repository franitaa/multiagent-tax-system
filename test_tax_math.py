from tax_math import (
    calculate_income_tax,
    calculate_standard_deduction,
    calculate_senior_deduction,
    calculate_taxable_social_security,
)

# Standard deduction tests

def test_single_standard_deduction():
    result = calculate_standard_deduction("single")
    assert result["value"] == 15750


def test_married_filing_jointly():
    result = calculate_standard_deduction("married_filing_jointly")
    assert result["value"] == 31500


def test_head_of_household():
    result = calculate_standard_deduction("head_of_household")
    assert result["value"] == 23625


def test_single_age_65():
    result = calculate_standard_deduction(
        "single",
        age_65_or_older=True,
    )
    assert result["value"] == 17750


def test_single_age_and_blindness():
    result = calculate_standard_deduction(
        "single",
        age_65_or_older=True,
        blind=True,
    )
    assert result["value"] == 19750


def test_both_spouses_age_65():
    result = calculate_standard_deduction(
        "married_filing_jointly",
        age_65_or_older=True,
        spouse_age_65_or_older=True,
    )
    assert result["value"] == 34700


def test_invalid_filing_status():
    try:
        calculate_standard_deduction("unknown")
    except ValueError:
        return
    raise AssertionError("Expected ValueError for invalid filing status")


# Senior deduction tests

def test_senior_deduction_below_threshold():
    result = calculate_senior_deduction(
        magi=50000,
        qualifying_people=1,
        filing_status="single",
    )
    assert result["value"] == 6000


def test_senior_deduction_at_threshold():
    result = calculate_senior_deduction(
        magi=75000,
        qualifying_people=1,
        filing_status="single",
    )
    assert result["value"] == 6000


def test_senior_deduction_phaseout():
    result = calculate_senior_deduction(
        magi=85000,
        qualifying_people=1,
        filing_status="single",
    )
    assert result["value"] == 5400


def test_senior_deduction_fully_phased_out():
    result = calculate_senior_deduction(
        magi=175000,
        qualifying_people=1,
        filing_status="single",
    )
    assert result["value"] == 0


def test_two_qualifying_people_joint_return():
    result = calculate_senior_deduction(
        magi=150000,
        qualifying_people=2,
        filing_status="married_filing_jointly",
    )
    assert result["value"] == 12000


def test_taxable_social_security_below_threshold():
    result = calculate_taxable_social_security(
        benefits=10000,
        other_income=10000,
        tax_exempt_interest=0,
        filing_status="single",
    )
    assert result["value"] == 0

def test_taxable_social_security_above_threshold():
    result = calculate_taxable_social_security(
        benefits=10000,
        other_income=35000,
        tax_exempt_interest=0,
        filing_status="single",
    )
    assert result["value"] == 8500

def test_taxable_social_security_middle_range():
    result = calculate_taxable_social_security(
        benefits=10000,
        other_income=25000,
        tax_exempt_interest=0,
        filing_status="single",
    )
    assert result["value"] == 2500

def test_taxable_social_security_upper_range():
    result = calculate_taxable_social_security(
        benefits=6000,
        other_income=32000,
        tax_exempt_interest=0,
        filing_status="single",
    )
    assert result["value"] == 3850

def test_income_tax_single():
    result = calculate_income_tax(
        taxable_income=10000,
        filing_status="single",
    )
    assert result["value"] == 1000
    assert result["tool"] == "calculate_income_tax"
    assert result["inputs"]["taxable_income"] == 10000

# Run all tests when this file is executed directly

if __name__ == "__main__":
    test_single_standard_deduction()
    test_married_filing_jointly()
    test_head_of_household()
    test_single_age_65()
    test_single_age_and_blindness()
    test_both_spouses_age_65()
    test_invalid_filing_status()

    test_senior_deduction_below_threshold()
    test_senior_deduction_at_threshold()
    test_senior_deduction_phaseout()
    test_senior_deduction_fully_phased_out()
    test_two_qualifying_people_joint_return()

    test_taxable_social_security_below_threshold()
    test_taxable_social_security_middle_range()

    test_taxable_social_security_upper_range()
    print("All tax math tests passed!")


def test_income_tax_2025_12_percent_bracket_tops():
    # Rev. Proc. 2024-40: single 12% bracket ends at 48,475; joint at 96,950.
    # Single 48,475: 1,192.50 + 0.12 * (48,475 - 11,925) = 5,578.50
    assert calculate_income_tax(48475, "single")["value"] == 5578.5
    # Joint 96,950: 2,385 + 0.12 * (96,950 - 23,850) = 11,157.00
    assert calculate_income_tax(96950, "married_filing_jointly")["value"] == 11157.0


# ---- CMP-2 edge cases, hand-calculated from Assignment 7 section 3.2 thresholds ----------------
import pytest  # noqa: E402

from tax_math import (  # noqa: E402
    calculate_senior_deduction,
    calculate_standard_deduction,
    calculate_taxable_social_security,
)


def ss(benefits, other, status="single", exempt=0):
    return calculate_taxable_social_security(benefits, other, exempt, status)["value"]


def test_ss_nothing_taxable_exactly_at_base_amounts():
    assert ss(20000, 15000) == 0                 # provisional 25,000 = single base
    assert ss(20000, 22000, "married_filing_jointly") == 0  # provisional 32,000 = joint base


def test_ss_first_dollar_over_base_is_taxed_at_fifty_percent():
    assert ss(20000, 22001, "married_filing_jointly") == 0.5


def test_ss_joint_upper_tier():
    # provisional 40,000 + 15,000 = 55,000; first tier 0.5*12,000 = 6,000;
    # above 44,000: 0.85 * 11,000 = 9,350; total 15,350 (cap 25,500 not reached)
    assert ss(30000, 40000, "married_filing_jointly") == 15350


def test_ss_never_exceeds_eighty_five_percent_of_benefits():
    assert ss(10000, 100000) == 8500


def test_ss_zero_benefits_and_negative_inputs():
    assert ss(0, 50000) == 0
    with pytest.raises(ValueError):
        ss(-1, 0)


def test_senior_deduction_joint_threshold_and_phaseout_per_person():
    joint = lambda magi: calculate_senior_deduction(magi, 2, "married_filing_jointly")["value"]  # noqa: E731
    assert joint(150000) == 12000
    assert joint(160000) == 12000 - 0.06 * 10000 * 2  # 10,800
    assert calculate_senior_deduction(85000, 1, "single")["value"] == 5400  # 6,000 - 0.06*10,000
    assert calculate_senior_deduction(50000, 0, "single")["value"] == 0


def test_senior_deduction_rejects_bad_input():
    with pytest.raises(ValueError):
        calculate_senior_deduction(-1, 1, "single")
    with pytest.raises(ValueError):
        calculate_senior_deduction(1000, 2, "single")


def test_standard_deduction_chart_corners():
    assert calculate_standard_deduction("married_filing_separately")["value"] == 15750
    # qualifying surviving spouse is "otherwise": 1,600 per box
    assert calculate_standard_deduction("qualifying_surviving_spouse", age_65_or_older=True)["value"] == 33100
    # head of household is unmarried: 2,000 per box
    assert calculate_standard_deduction("head_of_household", age_65_or_older=True, blind=True)["value"] == 27625
    # four boxes on a joint return: 31,500 + 4 * 1,600
    assert calculate_standard_deduction("married_filing_jointly", True, True, True, True)["value"] == 37900


def test_income_tax_zero_and_bracket_boundaries():
    assert calculate_income_tax(0, "single")["value"] == 0
    assert calculate_income_tax(17000, "head_of_household")["value"] == 1700
    assert calculate_income_tax(23850, "married_filing_jointly")["value"] == 2385
    # single 103,350: 1,192.50 + 4,386 + 0.22 * (103,350 - 48,475) = 17,651.00
    assert calculate_income_tax(103350, "single")["value"] == 17651.0
    with pytest.raises(ValueError):
        calculate_income_tax(-1, "single")
