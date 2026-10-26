"""STUB. Owned by the Eligibility & Rules teammate."""

from datetime import datetime

from src.state import (
    OUT_OF_SCOPE,
    SOURCE_CONFLICT,
    FORM_1099R_BOX_2B,
    TAX_ADVICE_REQUEST,
    FILING_STATUS_AMBIGUITY,
    EXPLOITATION_SIGNS,
)


VALID_FILING_STATUSES = {
    "single",
    "mfj",
    "mfs",
    "hoh",
    "qss",
}


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def _fact_value(facts, key, default=None):
    """
    Extract a value from a fact stored as:

    {
        "value": ...,
        "source": ...
    }
    """
    item = facts.get(key)

    if isinstance(item, dict):
        return item.get("value", default)

    return default


def _qualifies_for_1040sr(dob=None, age=None):
    """
    Determine Form 1040-SR eligibility for tax year 2025.

    Assignment rule:
    born before January 2, 1961.

    The age fallback is retained because the current Intake stub
    provides age rather than DOB.
    """

    if dob:
        try:
            birth_date = datetime.strptime(
                dob,
                "%Y-%m-%d"
            )

            cutoff = datetime(1961, 1, 2)

            return birth_date < cutoff

        except (ValueError, TypeError):
            return None

    if age is not None:
        return age >= 65

    return None


def _count_age_blindness_boxes(
    taxpayer_age_65_or_older=False,
    taxpayer_blind=False,
    spouse_age_65_or_older=False,
    spouse_blind=False,
):
    """
    Count Form 1040-SR line 12d age/blindness boxes.

    This agent counts boxes only.
    It does NOT calculate the dollar deduction.
    """

    return sum([
        bool(taxpayer_age_65_or_older),
        bool(taxpayer_blind),
        bool(spouse_age_65_or_older),
        bool(spouse_blind),
    ])


def _resolved_conditions(view):
    """
    Return escalation conditions that have already been resolved
    by a human.

    The handoff contract says an agent must not repeatedly raise
    the same condition after a human has resolved it.
    """

    resolved = set()

    for decision in view.get(
        "human_decisions",
        []
    ):
        condition = decision.get("condition")

        if condition:
            resolved.add(condition)

    return resolved


def _document_kinds(extracted):
    """
    Return normalized document kinds found by the Extraction agent.
    """

    kinds = set()

    for record in extracted.values():

        if not isinstance(record, dict):
            continue

        kind = record.get("kind")

        if kind:
            kinds.add(
                str(kind).strip().lower()
            )

    return kinds


def _field_value(record, field_name, default=None):
    """
    Read an extracted document field.

    Example:

    {
        "fields": {
            "box_2b": {
                "value": True,
                "source": "doc-1"
            }
        }
    }
    """

    fields = record.get(
        "fields",
        {}
    )

    item = fields.get(field_name)

    if isinstance(item, dict):
        return item.get(
            "value",
            default
        )

    if item is not None:
        return item

    return default


def _has_1099r_box_2b(extracted):
    """
    Check whether any extracted 1099-R has
    'taxable amount not determined' checked.
    """

    for record in extracted.values():

        if not isinstance(record, dict):
            continue

        kind = str(
            record.get("kind", "")
        ).strip().lower()

        if kind not in {
            "1099-r",
            "1099r",
        }:
            continue

        value = _field_value(
            record,
            "box_2b",
            False
        )

        if bool(value):
            return True

    return False


def _make_escalation(
    condition,
    reason,
    eligibility,
):
    """
    Standard escalation response for the Rules agent.
    """

    return {
        "eligibility": eligibility,

        "escalation": {
            "pending": True,
            "condition": condition,
            "reason": reason,
            "raised_by": "rules",
        },

        "handoff_request": {
            "to": "human",
            "reason": condition,
        },
    }


# ---------------------------------------------------------------------
# Main Rules Agent
# ---------------------------------------------------------------------

def run(view, tools):
    """
    Eligibility & Rules Agent.

    Allowed reads:
    - facts
    - extracted
    - session_summary
    - escalation
    - human_decisions

    Allowed writes:
    - eligibility
    - escalation
    - handoff_request
    """

    facts = view.get(
        "facts",
        {}
    )

    extracted = view.get(
        "extracted",
        {}
    )

    resolved = _resolved_conditions(
        view
    )

    # -----------------------------------------------------------------
    # Read taxpayer information
    # -----------------------------------------------------------------

    age = _fact_value(
        facts,
        "age"
    )

    taxpayer_dob = _fact_value(
        facts,
        "taxpayer_dob"
    )

    filing_status = _fact_value(
        facts,
        "filing_status_claim"
    )

    spouse_age = _fact_value(
        facts,
        "spouse_age"
    )

    spouse_dob = _fact_value(
        facts,
        "spouse_dob"
    )

    taxpayer_blind = _fact_value(
        facts,
        "taxpayer_blind",
        False
    )

    spouse_blind = _fact_value(
        facts,
        "spouse_blind",
        False
    )

    # -----------------------------------------------------------------
    # Prepare result
    # -----------------------------------------------------------------

    eligibility = {
        "eligible_1040sr": None,
        "taxpayer_qualifies": None,
        "spouse_qualifies": None,

        "filing_status": filing_status,
        "filing_status_valid": False,

        "age_blindness_boxes": 0,

        "in_scope": True,

        "applicable_rules": [],

        "out_of_scope_reasons": [],

        "citations": [],
    }

    # -----------------------------------------------------------------
    # Missing required information
    # -----------------------------------------------------------------

    missing = []

    if (
        age is None
        and taxpayer_dob is None
    ):
        missing.append(
            "taxpayer age or date of birth"
        )

    if filing_status is None:
        missing.append(
            "filing status"
        )

    if missing:

        return {
            "eligibility": eligibility,

            "handoff_request": {
                "to": "intake",

                "reason": (
                    "Missing required information: "
                    + ", ".join(missing)
                ),
            },
        }

    # -----------------------------------------------------------------
    # Validate filing status
    # -----------------------------------------------------------------

    normalized_status = (
        str(filing_status)
        .strip()
        .lower()
    )

    eligibility[
        "filing_status"
    ] = normalized_status

    eligibility[
        "filing_status_valid"
    ] = (
        normalized_status
        in VALID_FILING_STATUSES
    )

    eligibility["citations"].append(
        "Assignment 7 §3.3"
    )

    if not eligibility[
        "filing_status_valid"
    ]:

        eligibility["in_scope"] = False

        eligibility[
            "out_of_scope_reasons"
        ].append(
            "Unsupported filing status"
        )

        if (
            OUT_OF_SCOPE
            not in resolved
        ):

            return _make_escalation(
                OUT_OF_SCOPE,

                (
                    "Unsupported filing "
                    f"status: {filing_status}"
                ),

                eligibility,
            )

    # -----------------------------------------------------------------
    # Filing-status ambiguity
    # -----------------------------------------------------------------

    filing_status_ambiguous = (
        _fact_value(
            facts,
            "filing_status_ambiguous",
            False
        )
    )

    spouse_died_during_tax_year = (
        _fact_value(
            facts,
            "spouse_died_during_tax_year",
            False
        )
    )

    if (
        filing_status_ambiguous
        or spouse_died_during_tax_year
    ):

        if (
            FILING_STATUS_AMBIGUITY
            not in resolved
        ):

            return _make_escalation(
                FILING_STATUS_AMBIGUITY,

                (
                    "Filing status requires "
                    "human review."
                ),

                eligibility,
            )

    # -----------------------------------------------------------------
    # Form 1040-SR eligibility
    # -----------------------------------------------------------------

    taxpayer_qualifies = (
        _qualifies_for_1040sr(
            dob=taxpayer_dob,
            age=age
        )
    )

    spouse_qualifies = (
        _qualifies_for_1040sr(
            dob=spouse_dob,
            age=spouse_age
        )
    )

    eligibility[
        "taxpayer_qualifies"
    ] = taxpayer_qualifies

    eligibility[
        "spouse_qualifies"
    ] = spouse_qualifies

    if normalized_status == "mfj":

        eligible_1040sr = (
            taxpayer_qualifies is True
            or spouse_qualifies is True
        )

    else:

        eligible_1040sr = (
            taxpayer_qualifies is True
        )

    eligibility[
        "eligible_1040sr"
    ] = eligible_1040sr

    eligibility[
        "applicable_rules"
    ].append(
        "1040-SR eligibility"
    )

    eligibility["citations"].append(
        "Assignment 7 §3.2 Rule 1"
    )

    if not eligible_1040sr:

        eligibility["in_scope"] = False

        eligibility[
            "out_of_scope_reasons"
        ].append(
            "Not eligible for Form 1040-SR"
        )

        if (
            OUT_OF_SCOPE
            not in resolved
        ):

            return _make_escalation(
                OUT_OF_SCOPE,

                (
                    "Taxpayer does not meet "
                    "Form 1040-SR eligibility."
                ),

                eligibility,
            )

    # -----------------------------------------------------------------
    # Age / blindness boxes
    # -----------------------------------------------------------------

    taxpayer_age_65_or_older = (
        taxpayer_qualifies is True
    )

    spouse_age_65_or_older = (
        spouse_qualifies is True
    )

    age_blindness_boxes = (
        _count_age_blindness_boxes(

            taxpayer_age_65_or_older=
                taxpayer_age_65_or_older,

            taxpayer_blind=
                taxpayer_blind,

            spouse_age_65_or_older=
                spouse_age_65_or_older,

            spouse_blind=
                spouse_blind,
        )
    )

    eligibility[
        "age_blindness_boxes"
    ] = age_blindness_boxes

    eligibility[
        "applicable_rules"
    ].append(
        "Standard deduction age/blindness rule"
    )

    eligibility["citations"].append(
        "Assignment 7 §3.2 Rule 2"
    )

    # -----------------------------------------------------------------
    # Senior deduction applicability
    # -----------------------------------------------------------------

    if (
        taxpayer_age_65_or_older
        or spouse_age_65_or_older
    ):

        eligibility[
            "applicable_rules"
        ].append(
            "Schedule 1-A enhanced senior deduction"
        )

        eligibility["citations"].append(
            "Assignment 7 §3.2 Rule 3"
        )

    # -----------------------------------------------------------------
    # Social Security rule dependency
    # -----------------------------------------------------------------

    document_kinds = _document_kinds(
        extracted
    )

    if (
        "ssa-1099" in document_kinds
        or "ssa1099" in document_kinds
    ):

        eligibility[
            "applicable_rules"
        ].append(
            "Taxable Social Security worksheet"
        )

        eligibility["citations"].append(
            "Assignment 7 §3.2 Rule 4"
        )

    # -----------------------------------------------------------------
    # 1099-R Box 2b
    # -----------------------------------------------------------------

    box_2b_from_facts = (
        _fact_value(
            facts,
            "has_1099r_taxable_amount_not_determined",
            False
        )
    )

    box_2b_from_documents = (
        _has_1099r_box_2b(
            extracted
        )
    )

    if (
        box_2b_from_facts
        or box_2b_from_documents
    ):

        eligibility["in_scope"] = False

        eligibility[
            "out_of_scope_reasons"
        ].append(
            "1099-R taxable amount not determined"
        )

        if (
            FORM_1099R_BOX_2B
            not in resolved
        ):

            return _make_escalation(
                FORM_1099R_BOX_2B,

                (
                    "1099-R Box 2b indicates "
                    "taxable amount not determined."
                ),

                eligibility,
            )

    # -----------------------------------------------------------------
    # Standard-deduction exception conditions
    # -----------------------------------------------------------------

    dependent = _fact_value(
        facts,
        "taxpayer_can_be_claimed_as_dependent",
        False
    )

    spouse_itemizes = _fact_value(
        facts,
        "spouse_itemizes",
        False
    )

    dual_status_alien = _fact_value(
        facts,
        "dual_status_alien",
        False
    )

    standard_deduction_exceptions = []

    if dependent:
        standard_deduction_exceptions.append(
            "Taxpayer can be claimed as a dependent"
        )

    if spouse_itemizes:
        standard_deduction_exceptions.append(
            "Separately filing spouse itemizes"
        )

    if dual_status_alien:
        standard_deduction_exceptions.append(
            "Dual-status alien"
        )

    if standard_deduction_exceptions:

        eligibility["in_scope"] = False

        eligibility[
            "out_of_scope_reasons"
        ].extend(
            standard_deduction_exceptions
        )

        if (
            OUT_OF_SCOPE
            not in resolved
        ):

            return _make_escalation(
                OUT_OF_SCOPE,

                "; ".join(
                    standard_deduction_exceptions
                ),

                eligibility,
            )

    # -----------------------------------------------------------------
    # Other assignment out-of-scope conditions
    # -----------------------------------------------------------------

    out_of_scope_checks = [
        (
            "has_itemized_deductions",
            "Itemized deductions / Schedule A",
        ),

        (
            "has_self_employment_income",
            "Self-employment / Schedule C",
        ),

        (
            "has_rental_income",
            "Rental income / Schedule E",
        ),

        (
            "has_capital_gains_schedule_d",
            "Capital gains requiring Schedule D",
        ),

        (
            "has_digital_assets",
            "Digital assets",
        ),

        (
            "has_foreign_income_or_accounts",
            "Foreign income or accounts",
        ),

        (
            "has_amended_or_prior_year_return",
            "Amended or prior-year return",
        ),

        (
            "has_state_return",
            "State return",
        ),
    ]

    detected_out_of_scope = []

    for fact_name, reason in out_of_scope_checks:

        if _fact_value(
            facts,
            fact_name,
            False
        ):

            detected_out_of_scope.append(
                reason
            )

    if detected_out_of_scope:

        eligibility["in_scope"] = False

        eligibility[
            "out_of_scope_reasons"
        ].extend(
            detected_out_of_scope
        )

        eligibility["citations"].append(
            "Assignment 7 §3.3"
        )

        if (
            OUT_OF_SCOPE
            not in resolved
        ):

            return _make_escalation(
                OUT_OF_SCOPE,

                "; ".join(
                    detected_out_of_scope
                ),

                eligibility,
            )

    # -----------------------------------------------------------------
    # Source conflict
    # -----------------------------------------------------------------

    source_conflict = _fact_value(
        facts,
        "document_user_conflict",
        False
    )

    if (
        source_conflict
        and SOURCE_CONFLICT
        not in resolved
    ):

        return _make_escalation(
            SOURCE_CONFLICT,

            (
                "Unresolved conflict between "
                "taxpayer information and document."
            ),

            eligibility,
        )

    # -----------------------------------------------------------------
    # Tax advice request
    # -----------------------------------------------------------------

    tax_advice_requested = (
        _fact_value(
            facts,
            "tax_advice_requested",
            False
        )
    )

    if (
        tax_advice_requested
        and TAX_ADVICE_REQUEST
        not in resolved
    ):

        return _make_escalation(
            TAX_ADVICE_REQUEST,

            (
                "Request involves tax advice, "
                "planning, or optimization."
            ),

            eligibility,
        )

    # -----------------------------------------------------------------
    # Financial exploitation
    # -----------------------------------------------------------------

    exploitation_flag = (
        _fact_value(
            facts,
            "financial_exploitation_flag",
            False
        )
    )

    if (
        exploitation_flag
        and EXPLOITATION_SIGNS
        not in resolved
    ):

        return _make_escalation(
            EXPLOITATION_SIGNS,

            (
                "Possible financial exploitation "
                "or third-party pressure."
            ),

            eligibility,
        )

    # -----------------------------------------------------------------
    # Successful rules evaluation
    # -----------------------------------------------------------------

    return {
        "eligibility": eligibility,

        "handoff_request": {
            "to": "computation",

            "reason": (
                "Eligibility and scope checks passed"
            ),
        },
    }
