from provenance import ProvenanceRecord


example: ProvenanceRecord = {
    "value": 15750,
    "formula": "2025 base standard deduction",
    "inputs": {"filing_status": "single"},
    "source": "2025 standard deduction rule",
    "tool": "calculate_standard_deduction",
}

print(example)
