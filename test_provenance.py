from provenance import ProvenanceRecord


example: ProvenanceRecord = {
    "value": 15750,
    "formula": "2025 base standard deduction",
    "inputs": {"filing_status": "single"},
    "source": "2025 standard deduction rule",
    "tool": "calculate_standard_deduction",
}

required_fields = {"value", "formula", "inputs", "source", "tool"}

assert set(example.keys()) == required_fields
assert example["value"] == 15750
assert example["inputs"]["filing_status"] == "single"

print("All provenance record tests passed!")

