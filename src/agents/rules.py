"""STUB. Owned by the Eligibility & Rules teammate."""

from datetime import datetime
from typing import Any

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

YES_NO_NOT_SURE = {"yes", "no", "not_sure"}

# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------



def _fact_record(facts: dict[str, Any], name: str) -> dict[str, Any] | None:
    record = facts.get(name)
    return record if isinstance(record, dict) else None


def _fact_value(
    facts: dict[str, Any],
    name: str,
    default: Any = None,
) -> Any:
    record = _fact_record(facts, name)
    return record.get("value", default) if record is not None else default


def _fact_source(
    facts: dict[str, Any],
    name: str,
    default: Any = None,
) -> Any:
    record = _fact_record(facts, name)
    return record.get("source", default) if record is not None else default


def _normalize(value: Any) -> str | None:
    if value is None:
        return None
    return str(value).strip().lower()


def _is_yes(value: Any) -> bool:
    return _normalize(value) == "yes"


def _is_no(value: Any) -> bool:
    return _normalize(value) == "no"


def _is_not_sure(value: Any) -> bool:
    return _normalize(value) == "not_sure"


def _is_valid_yes_no_not_sure(value: Any) -> bool:
    return _normalize(value) in YES_NO_NOT_SURE


# -----------------------------------------------------------------------------
# Escalation and compatibility helpers
# -----------------------------------------------------------------------------


def _resolved_conditions(view: dict[str, Any]) -> set[str]:
    """Conditions a human resolved with a continue decision."""

    return {
        decision["condition"]
        for decision in view.get("human_decisions", [])
        if isinstance(decision, dict)
        and decision.get("decision") == "continue"
        and decision.get("condition")
    }


def _make_escalation(
    condition: str,
    reason: str,
    eligibility: dict[str, Any],
) -> dict[str, Any]:
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


def _return_to_intake(
    eligibility: dict[str, Any],
    reason: str,
) -> dict[str, Any]:
    return {
        "eligibility": eligibility,
        "handoff_request": {
            "to": "intake",
            "reason": reason,
        },
    }


def _preserve_pending_escalation(
    view: dict[str, Any],
    eligibility: dict[str, Any],
) -> dict[str, Any] | None:
    """Preserve a safety condition already raised by Intake or another agent."""

    escalation = view.get("escalation")
    if not isinstance(escalation, dict) or not escalation.get("pending"):
        return None

    condition = escalation.get("condition")
    if not condition:
        return None

    return {
        "eligibility": eligibility,
        "escalation": escalation,
        "handoff_request": {
            "to": "human",
            "reason": condition,
        },
    }


# -----------------------------------------------------------------------------
# Filing status
# -----------------------------------------------------------------------------


def _human_filing_status_override(facts: dict[str, Any]) -> str | None:
    """Use the volunteer's filing-status decision when it exists."""

    value = _normalize(_fact_value(facts, "filing_status"))
    source = _fact_source(facts, "filing_status", "")

    if (
        value in VALID_FILING_STATUSES
        and source == "human:FILING_STATUS_AMBIGUITY"
    ):
        return value

    return None


def _derive_filing_status(
    facts: dict[str, Any],
) -> tuple[str | None, bool, str | None]:
    """Derive status from Intake facts; return status, ambiguous, reason."""

    override = _human_filing_status_override(facts)
    if override is not None:
        return override, False, "Human filing-status override applied"

    married_dec31 = _fact_value(facts, "married_dec31")
    file_jointly = _fact_value(facts, "file_jointly")
    household_situation = _normalize(
        _fact_value(facts, "household_situation")
    )

    # Narrow compatibility fallback for older repository fixtures. Real Intake
    # does not write this field, so it is never preferred over the shared facts.
    legacy_claim = _normalize(_fact_value(facts, "filing_status_claim"))
    if married_dec31 is None and legacy_claim in VALID_FILING_STATUSES:
        return legacy_claim, False, "Legacy fixture filing-status fallback"

    if _is_not_sure(married_dec31):
        return None, True, "married_dec31 is not_sure"

    if _is_yes(married_dec31):
        if _is_not_sure(file_jointly):
            return None, True, "file_jointly is not_sure"
        if _is_yes(file_jointly):
            return "mfj", False, None
        if _is_no(file_jointly):
            return "mfs", False, None
        return None, True, "file_jointly is missing or invalid"

    if _is_no(married_dec31):
        if household_situation in {None, "", "not_sure"}:
            return None, True, "household_situation is missing or not_sure"

        if household_situation == "single":
            return "single", False, None

        if household_situation == "caring_for_someone":
            # The shared answer-name contract does not contain every fact needed
            # to prove Head of Household status. Do not guess; ask a volunteer.
            return (
                None,
                True,
                "Potential Head of Household status requires human review",
            )

        if household_situation == "widowed":
            spouse_death_year = _fact_value(facts, "spouse_death_year")

            if spouse_death_year is None or _is_not_sure(spouse_death_year):
                return None, True, "spouse_death_year is missing or not_sure"

            try:
                int(spouse_death_year)
            except (TypeError, ValueError):
                return None, True, "spouse_death_year is invalid"

            # The shared answer-name contract alone does not establish all QSS
            # requirements. A volunteer can resolve this and write the approved
            # status to facts['filing_status'].
            return (
                None,
                True,
                "Widowed filing status requires human review",
            )

        return (
            None,
            True,
            f"Unrecognized household_situation: {household_situation}",
        )

    return None, True, "married_dec31 is missing or invalid"


# -----------------------------------------------------------------------------
# Eligibility and document helpers
# -----------------------------------------------------------------------------


def _qualifies_for_1040sr(
    birth_date: Any = None,
    fallback_age: Any = None,
) -> bool | None:
    """2025 eligibility: born before January 2, 1961."""

    if birth_date is not None:
        if _is_not_sure(birth_date):
            return None

        try:
            parsed = datetime.strptime(str(birth_date), "%Y-%m-%d")
        except (TypeError, ValueError):
            return None

        return parsed < datetime(1961, 1, 2)

    # Compatibility only for the original stub scenarios.
    if fallback_age is not None:
        try:
            return int(fallback_age) >= 65
        except (TypeError, ValueError):
            return None

    return None


def _count_age_blindness_boxes(
    taxpayer_age_65: bool,
    taxpayer_blind: bool,
    spouse_age_65: bool,
    spouse_blind: bool,
) -> int:
    return sum(
        [
            taxpayer_age_65,
            taxpayer_blind,
            spouse_age_65,
            spouse_blind,
        ]
    )


def _field_value(
    record: dict[str, Any],
    field_name: str,
    default: Any = None,
) -> Any:
    item = record.get("fields", {}).get(field_name)
    if isinstance(item, dict):
        return item.get("value", default)
    return item if item is not None else default


def _has_1099r_box_2b(extracted: dict[str, Any]) -> bool:
    for record in extracted.values():
        if not isinstance(record, dict):
            continue

        if _normalize(record.get("kind")) not in {"1099-r", "1099r"}:
            continue

        value = _field_value(record, "box_2b", False)
        if value is True or _is_yes(value):
            return True

    return False


def _document_kinds(extracted: dict[str, Any]) -> set[str]:
    return {
        _normalize(record.get("kind"))
        for record in extracted.values()
        if isinstance(record, dict) and record.get("kind")
    }


# -----------------------------------------------------------------------------
# Main agent
# -----------------------------------------------------------------------------


def run(view: dict[str, Any], tools: Any) -> dict[str, Any]:
    facts = view.get("facts", {})
    extracted = view.get("extracted", {})
    resolved = _resolved_conditions(view)

    eligibility: dict[str, Any] = {
        "eligible_1040sr": None,
        "taxpayer_qualifies": None,
        "spouse_qualifies": None,
        "filing_status": "undetermined",
        "filing_status_valid": False,
        "age_blindness_boxes": 0,
        "in_scope": True,
        "applicable_rules": [],
        "out_of_scope_reasons": [],
        "citations": [],
    }

    pending = _preserve_pending_escalation(view, eligibility)
    if pending is not None:
        return pending

    taxpayer_birth_date = _fact_value(facts, "taxpayer_birth_date")
    spouse_birth_date = _fact_value(facts, "spouse_birth_date")

    # Compatibility only for old fixtures.
    taxpayer_age = _fact_value(facts, "age")
    spouse_age = _fact_value(facts, "spouse_age")

    if taxpayer_birth_date is None and taxpayer_age is None:
        return _return_to_intake(
            eligibility,
            "Missing required information: taxpayer_birth_date",
        )

    if _is_not_sure(taxpayer_birth_date):
        return _return_to_intake(
            eligibility,
            "taxpayer_birth_date is not_sure and needs follow-up",
        )

    filing_status, ambiguous, ambiguity_reason = _derive_filing_status(facts)

    if filing_status is not None:
        eligibility["filing_status"] = filing_status
        eligibility["filing_status_valid"] = (
            filing_status in VALID_FILING_STATUSES
        )

    eligibility["citations"].append("Assignment 7 §3.3")

    if ambiguous and FILING_STATUS_AMBIGUITY not in resolved:
        return _make_escalation(
            FILING_STATUS_AMBIGUITY,
            ambiguity_reason or "Filing status requires human review",
            eligibility,
        )

    taxpayer_qualifies = _qualifies_for_1040sr(
        birth_date=taxpayer_birth_date,
        fallback_age=taxpayer_age,
    )
    spouse_qualifies = _qualifies_for_1040sr(
        birth_date=spouse_birth_date,
        fallback_age=spouse_age,
    )

    eligibility["taxpayer_qualifies"] = taxpayer_qualifies
    eligibility["spouse_qualifies"] = spouse_qualifies

    if filing_status == "mfj":
        if taxpayer_qualifies is True or spouse_qualifies is True:
            eligible_1040sr: bool | None = True
        elif taxpayer_qualifies is False and spouse_qualifies is False:
            eligible_1040sr = False
        else:
            eligible_1040sr = None
    else:
        eligible_1040sr = taxpayer_qualifies

    eligibility["eligible_1040sr"] = eligible_1040sr
    eligibility["applicable_rules"].append("1040-SR eligibility")
    eligibility["citations"].append("Assignment 7 §3.2 Rule 1")

    if eligible_1040sr is None:
        return _return_to_intake(
            eligibility,
            "Unable to decide 1040-SR eligibility from the available birth dates",
        )

    if eligible_1040sr is False:
        eligibility["in_scope"] = False
        eligibility["out_of_scope_reasons"].append(
            "Not eligible for Form 1040-SR"
        )
        if OUT_OF_SCOPE not in resolved:
            return _make_escalation(
                OUT_OF_SCOPE,
                "Taxpayer does not meet Form 1040-SR eligibility.",
                eligibility,
            )

    taxpayer_blind_answer = _fact_value(facts, "taxpayer_blind", "no")
    spouse_blind_answer = _fact_value(facts, "spouse_blind", "no")

    if not _is_valid_yes_no_not_sure(taxpayer_blind_answer):
        return _return_to_intake(
            eligibility,
            "Invalid taxpayer_blind answer; expected yes, no, or not_sure",
        )

    if _is_not_sure(taxpayer_blind_answer):
        return _return_to_intake(
            eligibility,
            "taxpayer_blind is not_sure and needs follow-up",
        )

    spouse_is_relevant = filing_status in {"mfj", "mfs"}

    if spouse_is_relevant:
        if not _is_valid_yes_no_not_sure(spouse_blind_answer):
            return _return_to_intake(
                eligibility,
                "Invalid spouse_blind answer; expected yes, no, or not_sure",
            )
        if _is_not_sure(spouse_blind_answer):
            return _return_to_intake(
                eligibility,
                "spouse_blind is not_sure and needs follow-up",
            )

    taxpayer_age_65 = taxpayer_qualifies is True
    spouse_age_65 = spouse_is_relevant and spouse_qualifies is True

    eligibility["age_blindness_boxes"] = _count_age_blindness_boxes(
        taxpayer_age_65=taxpayer_age_65,
        taxpayer_blind=_is_yes(taxpayer_blind_answer),
        spouse_age_65=spouse_age_65,
        spouse_blind=(
            spouse_is_relevant and _is_yes(spouse_blind_answer)
        ),
    )
    eligibility["applicable_rules"].append(
        "Standard deduction age/blindness rule"
    )
    eligibility["citations"].append("Assignment 7 §3.2 Rule 2")

    if taxpayer_age_65 or spouse_age_65:
        eligibility["applicable_rules"].append(
            "Schedule 1-A enhanced senior deduction"
        )
        eligibility["citations"].append("Assignment 7 §3.2 Rule 3")

    document_kinds = _document_kinds(extracted)
    if "ssa-1099" in document_kinds or "ssa1099" in document_kinds:
        eligibility["applicable_rules"].append(
            "Taxable Social Security worksheet"
        )
        eligibility["citations"].append("Assignment 7 §3.2 Rule 4")

    if _has_1099r_box_2b(extracted):
        eligibility["in_scope"] = False
        eligibility["out_of_scope_reasons"].append(
            "1099-R taxable amount not determined"
        )
        if FORM_1099R_BOX_2B not in resolved:
            return _make_escalation(
                FORM_1099R_BOX_2B,
                "1099-R Box 2b indicates taxable amount not determined.",
                eligibility,
            )

    # Each tuple is: fact name, triggering answer, human-readable reason.
    screening_checks = [
        (
            "has_other_tax_forms",
            "yes",
            "Other tax forms outside the supported set",
        ),
        (
            "sold_stocks_or_property",
            "yes",
            "Stocks, funds, or property sold in 2025",
        ),
        (
            "business_or_rental_income",
            "yes",
            "Business, freelance, or rental income",
        ),
        (
            "foreign_income_or_accounts",
            "yes",
            "Foreign income or accounts",
        ),
        (
            "digital_assets",
            "yes",
            "Digital assets",
        ),
        (
            "can_be_claimed_as_dependent",
            "yes",
            "Taxpayer can be claimed as a dependent",
        ),
        (
            "us_resident_all_year",
            "no",
            "Taxpayer was not a US resident for all of 2025",
        ),
    ]

    detected_out_of_scope: list[str] = []

    for fact_name, trigger_value, reason in screening_checks:
        answer = _fact_value(facts, fact_name)

        # The contract says only use an answer if its question applies.
        if answer is None:
            continue

        normalized = _normalize(answer)

        # For scope-screening questions, uncertainty cannot safely continue.
        if normalized == "not_sure":
            detected_out_of_scope.append(
                f"{reason} (answer not_sure)"
            )
        elif normalized == trigger_value:
            detected_out_of_scope.append(reason)

    if filing_status in {"mfj", "mfs"}:
        spouse_can_be_claimed = _fact_value(
            facts,
            "spouse_can_be_claimed",
        )
        if _is_not_sure(spouse_can_be_claimed):
            detected_out_of_scope.append(
                "Whether the spouse can be claimed is not_sure"
            )
        elif _is_yes(spouse_can_be_claimed):
            detected_out_of_scope.append(
                "Spouse can be claimed as a dependent"
            )

    if filing_status == "mfs":
        spouse_itemizing = _fact_value(facts, "spouse_itemizing")
        if _is_not_sure(spouse_itemizing):
            detected_out_of_scope.append(
                "Whether the separately filing spouse itemizes is not_sure"
            )
        elif _is_yes(spouse_itemizing):
            detected_out_of_scope.append(
                "Separately filing spouse itemizes deductions"
            )

    if detected_out_of_scope:
        eligibility["in_scope"] = False
        eligibility["out_of_scope_reasons"].extend(
            detected_out_of_scope
        )
        eligibility["citations"].append("Assignment 7 §3.3")

        if OUT_OF_SCOPE not in resolved:
            return _make_escalation(
                OUT_OF_SCOPE,
                "; ".join(detected_out_of_scope),
                eligibility,
            )

    return {
        "eligibility": eligibility,
        "handoff_request": {
            "to": "computation",
            "reason": "Eligibility and scope checks passed",
        },
    }
