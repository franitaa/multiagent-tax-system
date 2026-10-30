"""Issue #27, step 2: amounts the taxpayer types in for an SSA-1099, 1099-INT or 1099-DIV go onto their
lines as direct-user-input records, and count as read (so the form is no longer flagged as not read).
Text amounts are not read here: a typed answer is a number."""
from src.agents import computation
from src.income_forms import TYPED_AMOUNTS, typed_amounts, unread_forms
from src.orchestration.access import ToolBox
from tests.test_unread_income_forms import NOT_READ, facts, read, skipped


def typed(**amounts):
    return {name: {"value": value, "source": "direct user input", "entered_by": "taxpayer", "entered_on": "2026-10-30"}
            for name, value in amounts.items()}


def run(extracted, **amounts):
    base = facts()
    update = computation.run({"facts": {**base, **typed(**amounts)}, "extracted": extracted, "eligibility": {}},
                             ToolBox("computation"))
    return update["computed"]


def test_every_typed_name_points_at_a_real_line_and_form():
    assert set(TYPED_AMOUNTS.values()) == {
        ("ssa1099", "line_6a"), ("ssa1099", "line_25b"), ("1099int", "line_2a"), ("1099int", "line_2b"),
        ("1099int", "line_25b"), ("1099div", "line_3a"), ("1099div", "line_3b"), ("1099div", "line_25b"),
    }


def test_a_typed_ssa_benefit_goes_on_line_6a_as_direct_input():
    line = run({}, ssa1099_benefits=20000.0)["line_6a"]
    assert line["value"] == 20000.0
    assert line["tool"] == "make_direct_input_provenance"
    assert line["inputs"]["field_name"] == "ssa1099_benefits"
    assert NOT_READ not in line["source"]


def test_a_typed_1099_int_and_1099_div_reach_their_lines():
    computed = run({}, int1099_taxable=300.0, int1099_tax_exempt=50.0, div1099_ordinary=700.0,
                   div1099_qualified=400.0)
    assert (computed["line_2b"]["value"], computed["line_2a"]["value"]) == (300.0, 50.0)
    assert (computed["line_3b"]["value"], computed["line_3a"]["value"]) == (700.0, 400.0)
    assert all(NOT_READ not in computed[k]["source"] for k in ("line_2b", "line_3b"))


def test_withholding_from_several_forms_is_summed_and_says_where_it_came_from():
    line = run({}, ssa1099_withheld=100.0, int1099_withheld=25.0)["line_25b"]
    assert line["value"] == 125.0
    assert "typed by taxpayer: int1099_withheld, ssa1099_withheld" in line["source"] or \
        "typed by taxpayer: ssa1099_withheld, int1099_withheld" in line["source"]


def test_a_typed_amount_counts_as_read_so_the_form_is_not_flagged():
    assert [f["form"] for f in unread_forms(facts(has_ssa_1099="yes"), {})] == ["SSA-1099"]
    assert unread_forms(facts(has_ssa_1099="yes", ssa1099_benefits=20000.0), {}) == []
    assert unread_forms(facts(has_1099_int="yes", int1099_taxable=300.0), {}) == []


def test_a_typed_amount_for_one_form_does_not_hide_another_unread_form():
    listed = unread_forms(facts(has_1099_div="yes", ssa1099_benefits=20000.0), {})
    assert [f["form"] for f in listed] == ["1099-DIV"]


def test_a_text_amount_is_not_a_typed_amount():
    assert typed_amounts({"ssa1099_benefits": {"value": "20000.00", "source": "user"}}, "line_6a") == []


def test_typed_and_document_amounts_on_the_same_line_are_both_counted():
    extracted = read("1099-INT", "doc-3", box_1=300.0)
    computed = run(extracted, int1099_taxable=200.0)
    assert computed["line_2b"]["value"] == 500.0
    assert "doc-3" in computed["line_2b"]["source"] and "int1099_taxable" in computed["line_2b"]["source"]


def test_a_skipped_form_with_a_typed_amount_on_another_line_still_says_not_read():
    extracted = skipped("SSA-1099")
    computed = run(extracted, int1099_taxable=300.0)
    assert NOT_READ in computed["line_6a"]["source"]
    assert computed["line_2b"]["value"] == 300.0


def test_forms_without_amounts_stops_listing_a_form_once_an_amount_is_typed():
    """PR #40 lists the forms with no held amount; a typed amount must clear its form. Skipped until
    #40 is merged (the function lives there), so it passes in either merge order."""
    import pytest
    import src.income_forms as income_forms
    forms_without_amounts = getattr(income_forms, "forms_without_amounts", None)
    if forms_without_amounts is None:
        pytest.skip("forms_without_amounts arrives with PR #40")

    assert forms_without_amounts(facts(has_ssa_1099="yes"), {}) == ["SSA-1099"]
    assert forms_without_amounts(facts(has_ssa_1099="yes", ssa1099_benefits=20000.0), {}) == []
    assert forms_without_amounts(facts(has_1099_int="yes", int1099_taxable=300.0), {}) == []
    # a typed amount for one form does not hide another form that has none
    assert forms_without_amounts(facts(has_1099_div="yes", ssa1099_benefits=20000.0), {}) == ["1099-DIV"]
