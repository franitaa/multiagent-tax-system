from provenance import (
    ProvenanceRecord,
    make_direct_input_provenance,
    make_provenance,
)


def test_provenance_record_fields():
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


def test_make_provenance():
    result = make_provenance(
        value=2500,
        formula="10000 * 0.25",
        inputs={"income": 10000, "rate": 0.25},
        source="Test calculation",
        tool="test_tool",
    )

    assert result["value"] == 2500
    assert result["formula"] == "10000 * 0.25"
    assert result["inputs"]["income"] == 10000
    assert result["source"] == "Test calculation"
    assert result["tool"] == "test_tool"


def test_direct_input_provenance():
    result = make_direct_input_provenance(
        value=1250,
        field_name="estimated_tax_payments",
    )

    assert result["value"] == 1250
    assert result["formula"] == "Direct user input; no calculation performed"
    assert result["inputs"]["field_name"] == "estimated_tax_payments"
    assert result["inputs"]["entered_value"] == 1250
    assert result["source"] == "User-provided value"
    assert result["tool"] == "make_direct_input_provenance"


def test_provenance_rejects_empty_source():
    try:
        make_provenance(100, "test formula", {}, "", "test_tool")
    except ValueError:
        return

    raise AssertionError("Expected ValueError for empty source")


if __name__ == "__main__":
    test_provenance_record_fields()
    test_make_provenance()
    test_direct_input_provenance()
    test_provenance_rejects_empty_source()
    print("All provenance record tests passed!")
