from tax_math import (
    calculate_standard_deduction,
    calculate_senior_deduction,
    calculate_taxable_social_security,
)


# CMP-2: Hand-calculated unit tests
# Expected values below are calculated independently by hand.


# --------------------------------------------------
# Standard deduction tests
# --------------------------------------------------

def test_single_standard_deduction():
    # Single base deduction = $15,750
    result = calculate_standard_deduction("single")
    assert result["value"] == 15750


def test_married_filing_jointly():
    # Joint base deduction = $31,500
    result = calculate_standard_deduction("married_filing_jointly")
    assert result["value"] == 31500


def test_head_of_household():
    # Head of household base deduction = $23,625
    result = calculate_standard_deduction("head_of_household")
    assert result["value"] == 23625


def test_single_age_65():
    # $15,750 base + $2,000 age adjustment = $17,750
    result = calculate_standard_deduction(
        "single",
        age_65_or_older=True,
    )
    assert result["value"] == 17750


def test_single_age_and_blindness():
    # $15,750 + $2,000 age + $2,000 blindness = $19,750
    result = calculate_standard_deduction(
        "single",
        age_65_or_older=True,
        blind=True,
    )
    assert result["value"] == 19750


def test_both_spouses_age_65():
    # $31,500 + $1,600 for each qualifying spouse = $34,700
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


# --------------------------------------------------
# Senior deduction tests
# --------------------------------------------------

def test_senior_deduction_below_threshold():
    # MAGI $50,000 is below $75,000; full $6,000 deduction
    result = calculate_senior_deduction(
        magi=50000,
        qualifying_people=1,
        filing_status="single",
    )
    assert result["value"] == 6000


def test_senior_deduction_at_threshold():
    # At $75,000, the phaseout has not started
    result = calculate_senior_deduction(
        magi=75000,
        qualifying_people=1,
        filing_status="single",
    )
    assert result["value"] == 6000


def test_senior_deduction_phaseout():
    # ($85,000 - $75,000) x 6% = $600 reduction
    # $6,000 - $600 = $5,400 deduction
    result = calculate_senior_deduction(
        magi=85000,
        qualifying_people=1,
        filing_status="single",
    )
    assert result["value"] == 5400


def test_senior_deduction_fully_phased_out():
    # ($175,000 - $75,000) x 6% = $6,000 reduction
    # $6,000 - $6,000 = $0 deduction
    result = calculate_senior_deduction(
        magi=175000,
        qualifying_people=1,
        filing_status="single",
    )
    assert result["value"] == 0


def test_two_qualifying_people_joint_return():
    # At joint MAGI $150,000, both $6,000 deductions remain
    result = calculate_senior_deduction(
        magi=150000,
        qualifying_people=2,
        filing_status="married_filing_jointly",
    )
    assert result["value"] == 12000


def test_joint_senior_deduction_phaseout():
    # ($160,000 - $150,000) x 6% x 2 people = $1,200 reduction
    # $12,000 - $1,200 = $10,800 deduction
    result = calculate_senior_deduction(
        magi=160000,
        qualifying_people=2,
        filing_status="married_filing_jointly",
    )
    assert result["value"] == 10800


# --------------------------------------------------
# Taxable Social Security tests
# --------------------------------------------------

def test_taxable_social_security_below_threshold():
    # Provisional income = $10,000 + $0 + ($10,000 / 2)
    # = $15,000, below the $25,000 single threshold
    result = calculate_taxable_social_security(
        benefits=10000,
        other_income=10000,
        tax_exempt_interest=0,
        filing_status="single",
    )
    assert result["value"] == 0


def test_taxable_social_security_middle_range():
    # Provisional income = $25,000 + $5,000 = $30,000
    # Excess over $25,000 = $5,000
    # Taxable benefits = 50% x $5,000 = $2,500
    result = calculate_taxable_social_security(
        benefits=10000,
        other_income=25000,
        tax_exempt_interest=0,
        filing_status="single",
    )
    assert result["value"] == 2500


def test_taxable_social_security_includes_tax_exempt_interest():
    # Provisional income = $20,000 + $10,000 + $5,000 = $35,000
    # First tier: $9,000 x 50% = $4,500
    # Above first tier: ($35,000 - $34,000) x 85% = $850
    # Total = $4,500 + $850 = $5,350
    result = calculate_taxable_social_security(
        benefits=10000,
        other_income=20000,
        tax_exempt_interest=10000,
        filing_status="single",
    )
    assert result["value"] == 5350


def test_taxable_social_security_upper_range():
    # Provisional income = $32,000 + $3,000 = $35,000
    # First tier: $9,000 x 50% = $4,500, capped at $3,000
    # Above first tier: $1,000 x 85% = $850
    # Total = $3,000 + $850 = $3,850
    result = calculate_taxable_social_security(
        benefits=6000,
        other_income=32000,
        tax_exempt_interest=0,
        filing_status="single",
    )
    assert result["value"] == 3850


def test_taxable_social_security_maximum_85_percent():
    # Maximum taxable benefits = $10,000 x 85% = $8,500
    result = calculate_taxable_social_security(
        benefits=10000,
        other_income=35000,
        tax_exempt_interest=0,
        filing_status="single",
    )
    assert result["value"] == 8500


def test_joint_social_security_at_base_threshold():
    # Joint provisional income = $27,000 + $5,000 = $32,000
    # At the $32,000 base threshold, taxable benefits = $0
    result = calculate_taxable_social_security(
        benefits=10000,
        other_income=27000,
        tax_exempt_interest=0,
        filing_status="married_filing_jointly",
    )
    assert result["value"] == 0


def test_joint_social_security_at_upper_threshold():
    # Joint provisional income = $39,000 + $5,000 = $44,000
    # At the upper threshold, first-tier taxable benefits = $5,000
    # This is 50% of $10,000 benefits; second-tier excess is $0
    result = calculate_taxable_social_security(
        benefits=10000,
        other_income=39000,
        tax_exempt_interest=0,
        filing_status="married_filing_jointly",
    )
    assert result["value"] == 5000


# --------------------------------------------------
# Run all tests when executed directly
# --------------------------------------------------

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
    test_joint_senior_deduction_phaseout()

    test_taxable_social_security_below_threshold()
    test_taxable_social_security_middle_range()
    test_taxable_social_security_includes_tax_exempt_interest()
    test_taxable_social_security_upper_range()
    test_taxable_social_security_maximum_85_percent()
    test_joint_social_security_at_base_threshold()
    test_joint_social_security_at_upper_threshold()

    print("All tax math tests passed!")
