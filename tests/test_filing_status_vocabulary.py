"""One vocabulary for the filing status.

The human gate and tax_math use long names ("married_filing_jointly"); Rules decides in short
codes ("mfj") and emits them in eligibility.filing_status. tax_math raises on a code, so only
"single" works end to end today. These are STRICT expected failures: when the team picks one
vocabulary (proposal: long names everywhere, Rules maps at its output) they pass, strict mode
fails the run, and the markers go. Owners: Matthew (Rules), Sahana (tax_math), orchestration
(this test and the handoff contract).
"""
import pytest

import tax_math
from src.agents import rules

REASON = ("Rules emits short codes (mfj) but tax_math and the human gate use long names "
          "(married_filing_jointly); tax_math raises 'Unsupported filing status: mfj'.")


def accepted_by_tax_math(status):
    tax_math.calculate_standard_deduction(status)


def decide(facts):
    return rules.run({"facts": {k: {"value": v, "source": "user"} for k, v in facts.items()},
                      "extracted": {}}, None)["eligibility"]


def test_single_works_end_to_end_today():
    result = decide({"taxpayer_birth_date": "1950-03-04", "married_dec31": "no",
                     "household_situation": "single"})
    accepted_by_tax_math(result["filing_status"])


@pytest.mark.xfail(strict=True, raises=ValueError, reason=REASON)
def test_a_joint_return_decided_by_rules_is_accepted_by_tax_math():
    result = decide({"taxpayer_birth_date": "1950-03-04", "spouse_birth_date": "1951-05-06",
                     "married_dec31": "yes", "file_jointly": "yes"})
    assert result["filing_status"]  # Rules did decide something
    accepted_by_tax_math(result["filing_status"])


@pytest.mark.xfail(strict=True, raises=ValueError, reason=REASON)
@pytest.mark.parametrize("status", sorted(rules.VALID_FILING_STATUSES))
def test_every_status_rules_can_emit_is_accepted_by_tax_math(status):
    if status == "single":
        pytest.skip("single is the same in both vocabularies")
    accepted_by_tax_math(status)
