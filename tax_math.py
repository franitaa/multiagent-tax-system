from provenance import ProvenanceRecord


def calculate_standard_deduction(
    filing_status: str,
    age_65_or_older: bool = False,
    blind: bool = False,
    spouse_age_65_or_older: bool = False,
    spouse_blind: bool = False,
) -> ProvenanceRecord:
    """Calculate the 2025 standard deduction, including age/blindness additions.

    Eligibility exceptions, such as dependent status or a spouse itemizing
    separately, must be checked before relying on the result.
    """
    deductions = {
        "single": 15750,
        "married_filing_separately": 15750,
        "married_filing_jointly": 31500,
        "qualifying_surviving_spouse": 31500,
        "head_of_household": 23625,
    }

    if filing_status not in deductions:
        raise ValueError(f"Unsupported filing status: {filing_status}")

    base_amount = deductions[filing_status]

    # Additional amount for each qualifying age/blindness condition.
    # Single and head of household: $2,000 per condition.
    # Other filing statuses: $1,600 per condition.
    if filing_status in ("single", "head_of_household"):
        additional_per_condition = 2000
    else:
        additional_per_condition = 1600

    additional_amount = 0

    if age_65_or_older:
        additional_amount += additional_per_condition

    if blind:
        additional_amount += additional_per_condition

    if filing_status in (
        "married_filing_jointly",
        "married_filing_separately",
    ):
        if spouse_age_65_or_older:
            additional_amount += 1600

        if spouse_blind:
            additional_amount += 1600

    total = base_amount + additional_amount

    return {
        "value": total,
        "formula": "base standard deduction + age/blindness additions",
        "inputs": {
            "filing_status": filing_status,
            "age_65_or_older": age_65_or_older,
            "blind": blind,
            "spouse_age_65_or_older": spouse_age_65_or_older,
            "spouse_blind": spouse_blind,
        },
        "source": (
            "2025 standard deduction rules in assignment requirements"
        ),
        "tool": "calculate_standard_deduction",
    }


def calculate_senior_deduction(
    magi: float,
    qualifying_people: int,
    filing_status: str,
) -> ProvenanceRecord:
    """Calculate the 2025 enhanced senior deduction.

    Provides up to $6,000 per qualifying person aged 65 or older.
    The deduction phases out at 6% of MAGI above the applicable threshold
    for each qualifying person.
    """
    valid_statuses = (
        "married_filing_jointly",
        "single",
        "married_filing_separately",
        "head_of_household",
        "qualifying_surviving_spouse",
    )

    if filing_status not in valid_statuses:
        raise ValueError(f"Unsupported filing status: {filing_status}")

    if magi < 0:
        raise ValueError("MAGI cannot be negative")

    if qualifying_people not in (0, 1, 2):
        raise ValueError("qualifying_people must be 0, 1, or 2")

    if filing_status != "married_filing_jointly" and qualifying_people > 1:
        raise ValueError(
            "Only joint filers can claim two qualifying people"
        )

    threshold = (
        150000 if filing_status == "married_filing_jointly" else 75000
    )

    maximum_deduction = 6000 * qualifying_people
    reduction = max(0, magi - threshold) * 0.06 * qualifying_people
    deduction = max(0, maximum_deduction - reduction)
    deduction = min(deduction, maximum_deduction)

    return {
        "value": round(deduction, 2),
        "formula": (
            "maximum deduction minus 6% of MAGI above the threshold "
            "per qualifying person, floored at zero"
        ),
        "inputs": {
            "magi": magi,
            "qualifying_people": qualifying_people,
            "filing_status": filing_status,
            "threshold": threshold,
            "maximum_deduction": maximum_deduction,
        },
        "source": (
            "2025 enhanced senior deduction rules in assignment requirements"
        ),
        "tool": "calculate_senior_deduction",
    }


def calculate_taxable_social_security(
    benefits: float,
    other_income: float,
    tax_exempt_interest: float,
    filing_status: str,
) -> ProvenanceRecord:
    """Calculate taxable Social Security using the assignment's thresholds.

    Provisional income equals other income, plus tax-exempt interest,
    plus half of Social Security benefits.

    This implements the assignment-focused threshold calculation.
    Additional IRS worksheet exceptions may require separate handling.
    """
    if benefits < 0 or other_income < 0 or tax_exempt_interest < 0:
        raise ValueError("Income and benefits cannot be negative")

    valid_statuses = (
        "single",
        "head_of_household",
        "married_filing_separately",
        "married_filing_jointly",
        "qualifying_surviving_spouse",
    )

    if filing_status not in valid_statuses:
        raise ValueError(f"Unsupported filing status: {filing_status}")

    if filing_status == "married_filing_jointly":
        base_amount = 32000
        upper_amount = 44000
        first_tier_width = 12000
    else:
        base_amount = 25000
        upper_amount = 34000
        first_tier_width = 9000

    provisional_income = (
        other_income + tax_exempt_interest + benefits / 2
    )

    if provisional_income <= base_amount:
        taxable_benefits = 0
    else:
        excess_over_base = provisional_income - base_amount

        # Calculate the portion within the first tier.
        amount_in_first_tier = min(
            excess_over_base,
            first_tier_width,
        )

        # Calculate the portion above the upper threshold.
        amount_above_first_tier = max(
            0,
            excess_over_base - first_tier_width,
        )

        # The first tier is limited to half of benefits.
        first_tier_taxable = min(
            benefits * 0.5,
            amount_in_first_tier * 0.5,
        )

        # The portion above the first tier is generally taxable at 85%.
        second_tier_taxable = amount_above_first_tier * 0.85

        # Taxable benefits cannot exceed 85% of total benefits.
        taxable_benefits = min(
            benefits * 0.85,
            first_tier_taxable + second_tier_taxable,
        )

    taxable_benefits = max(
        0,
        min(taxable_benefits, benefits * 0.85),
    )

    return {
        "value": round(taxable_benefits, 2),
        "formula": (
            "Taxable Social Security based on provisional income, "
            "the first-tier amount, and the 85% benefits limit"
        ),
        "inputs": {
            "benefits": benefits,
            "other_income": other_income,
            "tax_exempt_interest": tax_exempt_interest,
            "filing_status": filing_status,
            "provisional_income": provisional_income,
            "base_amount": base_amount,
            "upper_amount": upper_amount,
            "first_tier_width": first_tier_width,
        },
        "source": (
            "Social Security thresholds stated in the assignment requirements"
        ),
        "tool": "calculate_taxable_social_security",
    }

def calculate_income_tax(
    taxable_income: float,
    filing_status: str,
) -> ProvenanceRecord:
    """Calculate 2025 federal income tax using ordinary tax brackets.

    This simplified calculation is for ordinary taxable income only.
    Qualified dividends, capital gains, and other special tax situations
    are not handled by this function.
    """
    if taxable_income < 0:
        raise ValueError("taxable_income cannot be negative")

    brackets = {
        "single": [
            (11925, 0.10),
            (48475, 0.12),
            (103350, 0.22),
            (197300, 0.24),
            (250525, 0.32),
            (626350, 0.35),
            (float("inf"), 0.37),
        ],
        "married_filing_jointly": [
            (23850, 0.10),
            (96950, 0.12),
            (206700, 0.22),
            (394600, 0.24),
            (501050, 0.32),
            (751600, 0.35),
            (float("inf"), 0.37),
        ],
        "married_filing_separately": [
            (11925, 0.10),
            (48475, 0.12),
            (103350, 0.22),
            (197300, 0.24),
            (250525, 0.32),
            (375800, 0.35),
            (float("inf"), 0.37),
        ],
        "head_of_household": [
            (17000, 0.10),
            (64850, 0.12),
            (103350, 0.22),
            (197300, 0.24),
            (250500, 0.32),
            (626350, 0.35),
            (float("inf"), 0.37),
        ],
        "qualifying_surviving_spouse": [
            (23850, 0.10),
            (96950, 0.12),
            (206700, 0.22),
            (394600, 0.24),
            (501050, 0.32),
            (751600, 0.35),
            (float("inf"), 0.37),
        ],
    }

    if filing_status not in brackets:
        raise ValueError(f"Unsupported filing status: {filing_status}")

    remaining_income = taxable_income
    previous_limit = 0
    tax = 0.0

    for upper_limit, rate in brackets[filing_status]:
        amount_in_bracket = min(
            remaining_income,
            upper_limit - previous_limit,
        )
        tax += amount_in_bracket * rate
        remaining_income -= amount_in_bracket

        if remaining_income <= 0:
            break

        previous_limit = upper_limit

    tax = round(tax, 2)

    return {
        "value": tax,
        "formula": "2025 ordinary income tax brackets",
        "inputs": {
            "taxable_income": taxable_income,
            "filing_status": filing_status,
        },
        "source": "2025 IRS tax rate schedules",
        "tool": "calculate_income_tax",
    }

def sum_amounts(
    amounts: dict[str, float],
    label: str,
) -> ProvenanceRecord:
    """Add named amounts. `label` names the form line being produced."""
    total = round(sum(amounts.values()), 2)
    return {
        "value": total,
        "formula": f"{label} = " + (" + ".join(amounts) or "0"),
        "inputs": dict(amounts),
        "source": "Addition of the listed form lines",
        "tool": "sum_amounts",
    }


def subtract_amounts(
    start: float,
    subtract: dict[str, float],
    label: str,
    start_name: str = "start",
    floor_at_zero: bool = True,
) -> ProvenanceRecord:
    """Compute start minus the named amounts, optionally floored at zero."""
    result = round(start - sum(subtract.values()), 2)
    if floor_at_zero:
        result = max(0, result)
    return {
        "value": result,
        "formula": (
            f"{label} = {start_name} - " + (" - ".join(subtract) or "0")
            + (", not below zero" if floor_at_zero else "")
        ),
        "inputs": {start_name: start, **subtract},
        "source": "Subtraction of the listed form lines",
        "tool": "subtract_amounts",
    }
