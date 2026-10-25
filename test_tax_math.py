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
