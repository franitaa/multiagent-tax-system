"""Provenance records for monetary values in the tax system."""

from typing import Any, TypedDict


class ProvenanceRecord(TypedDict):
    """Explain where a tax value came from and how it was produced."""

    value: float | str
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
    """Create a provenance record for a calculated monetary value.

    Args:
        value: The resulting amount.
        formula: The calculation or explanation of how the amount was obtained.
        inputs: The input values used in the calculation.
        source: Where the value or applicable rule came from.
        tool: The function or tool that produced the value.

    Returns:
        A structured provenance record.
    """
    if not formula.strip():
        raise ValueError("Provenance formula must not be empty")
    if not source.strip():
        raise ValueError("Provenance source must not be empty")
    if not tool.strip():
        raise ValueError("Provenance tool must not be empty")

    return {
        "value": value,
        "formula": formula,
        "inputs": inputs,
        "source": source,
        "tool": tool,
    }


def make_direct_input_provenance(
    value: float | int,
    field_name: str,
) -> ProvenanceRecord:
    """Record a monetary value entered directly by the user.

    This records the origin of the value; it does not independently verify
    whether the user-entered amount is accurate.
    """
    if not field_name.strip():
        raise ValueError("Field name must not be empty")

    return make_provenance(
        value=value,
        formula="Direct user input; no calculation performed",
        inputs={"field_name": field_name, "entered_value": value},
        source="User-provided value",
        tool="make_direct_input_provenance",
    )
