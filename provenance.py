"""Provenance records for monetary values in the tax system."""

from datetime import date
from typing import Any, TypedDict


class ProvenanceRecord(TypedDict):
    """Explain where a tax value came from and how it was produced."""

    value: float | int
    formula: str
    inputs: dict[str, Any]
    source: str
    tool: str


def make_provenance(
    value: float | int,
    formula: str,
    inputs: dict[str, Any],
    source: str,
    tool: str,
) -> ProvenanceRecord:
    """Create a provenance record for a calculated monetary value."""
    if not isinstance(formula, str) or not formula.strip():
        raise ValueError("Provenance formula must not be empty")
    if not isinstance(source, str) or not source.strip():
        raise ValueError("Provenance source must not be empty")
    if not isinstance(tool, str) or not tool.strip():
        raise ValueError("Provenance tool must not be empty")

    return {
        "value": value,
        "formula": formula,
        "inputs": inputs.copy(),
        "source": source,
        "tool": tool,
    }


def make_direct_input_provenance(
    value: float | int,
    field_name: str,
    entered_by: str,
    entered_on: str | None = None,
) -> ProvenanceRecord:
    """Record a monetary value entered directly by a user."""
    if not isinstance(field_name, str) or not field_name.strip():
        raise ValueError("Field name must not be empty")
    if not isinstance(entered_by, str) or not entered_by.strip():
        raise ValueError("User attribution must not be empty")

    if entered_on is None:
        entered_on = date.today().isoformat()
    elif not isinstance(entered_on, str) or not entered_on.strip():
        raise ValueError("Entry date must not be empty")

    return make_provenance(
        value=value,
        formula="Direct user input; no calculation performed",
        inputs={
            "field_name": field_name,
            "entered_value": value,
            "entered_by": entered_by,
            "entered_on": entered_on,
        },
        source="direct user input",  # the label Review and docs/answer-names.md expect
        tool="make_direct_input_provenance",
    )
