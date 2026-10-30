"""One vocabulary for the filing status.

The human gate and tax_math use long names ("married_filing_jointly"); Rules decides in short
codes ("mfj") and maps them to long names at its output (FILING_STATUS_OUTPUT). These tests pin
that: every status Rules can emit must be accepted by tax_math, so a new code without a mapping
fails here instead of raising inside Computation.
"""
import pytest

import tax_math
from src.agents import rules

def accepted_by_tax_math(status):
    tax_math.calculate_standard_deduction(status)


def decide(facts):
    return rules.run({"facts": {k: {"value": v, "source": "user"} for k, v in facts.items()},
                      "extracted": {}}, None)["eligibility"]


def test_single_works_end_to_end_today():
    result = decide({"taxpayer_birth_date": "1950-03-04", "married_dec31": "no",
                     "household_situation": "single"})
    accepted_by_tax_math(result["filing_status"])


def test_a_joint_return_decided_by_rules_is_accepted_by_tax_math():
    result = decide({"taxpayer_birth_date": "1950-03-04", "spouse_birth_date": "1951-05-06",
                     "married_dec31": "yes", "file_jointly": "yes"})
    assert result["filing_status"] == "married_filing_jointly"
    accepted_by_tax_math(result["filing_status"])


@pytest.mark.parametrize("status", sorted(rules.VALID_FILING_STATUSES))
def test_every_status_rules_can_emit_is_accepted_by_tax_math(status):
    accepted_by_tax_math(rules.FILING_STATUS_OUTPUT[status])
