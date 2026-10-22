
from typing import Any, TypedDict

class ProvenanceRecord(TypedDict):
    """Explain where a tax value came from and how it was produced."""

    value: float | str
    formula: str
    inputs: dict[str, Any]
    source: str
    tool: str
