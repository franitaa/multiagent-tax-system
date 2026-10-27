import pytest

from provenance import make_direct_input_provenance, make_provenance


def test_provenance_record_fields():
    result = make_provenance(
        15750, "2025 base standard deduction",
        {"filing_status": "single"}, "2025 standard deduction rule",
        "calculate_standard_deduction",
    )
    assert set(result) == {"value", "formula", "inputs", "source", "tool"}
    assert result["value"] == 15750


def test_make_provenance():
    result = make_provenance(
        2500, "10000 * 0.25", {"income": 10000, "rate": 0.25},
        "Test calculation", "test_tool",
    )
    assert result["value"] == 2500
    assert result["inputs"]["income"] == 10000


def test_direct_input_provenance():
    result = make_direct_input_provenance(
        1250, "estimated_tax_payments", "taxpayer", "2026-10-26"
    )
    assert result["inputs"]["field_name"] == "estimated_tax_payments"
    assert result["inputs"]["entered_by"] == "taxpayer"
    assert result["inputs"]["entered_on"] == "2026-10-26"


def test_direct_input_defaults_to_current_date():
    result = make_direct_input_provenance(1250, "estimated_tax_payments", "taxpayer")
    assert result["inputs"]["entered_on"]


@pytest.mark.parametrize(
    ("formula", "source", "tool"),
    [("", "source", "tool"), ("formula", "", "tool"), ("formula", "source", "")],
)
def test_make_provenance_rejects_empty_required_text(formula, source, tool):
    with pytest.raises(ValueError):
        make_provenance(100, formula, {}, source, tool)


def test_direct_input_rejects_empty_field_name():
    with pytest.raises(ValueError):
        make_direct_input_provenance(100, "", "taxpayer")


def test_direct_input_rejects_empty_user():
    with pytest.raises(ValueError):
        make_direct_input_provenance(100, "income", "")
