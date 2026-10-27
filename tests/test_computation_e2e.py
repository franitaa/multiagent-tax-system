"""End-to-end Computation tests: dependency order, hand-calculated values, provenance on every
line, direct-input attribution, survival through the graph, and the click-to-inspect form."""
import pytest

from src.agents import computation
from src.draft_form import render_draft_html
from src.graph import build_graph
from src.orchestration.access import ToolBox
from src.scenarios import clean_case

KEYS = {"value", "formula", "inputs", "source", "tool"}


def doc(kind, **fields):
    return {"kind": kind, "fields": {k: {"value": v, "source": "d"} for k, v in fields.items()}}


def view(status="single", age=70, extracted=None, **facts):
    f = {"filing_status": {"value": status, "source": "user"}, "age": {"value": age, "source": "user"}}
    f.update({k: {"value": v, "source": "user"} for k, v in facts.items()})
    return {"facts": f, "extracted": extracted or {}, "eligibility": {}}


def compute(v):
    tools = ToolBox("computation")
    return computation.run(v, tools)["computed"], tools.calls


def test_hand_calculated_single_senior_with_social_security():
    # W-2 30,000 (withheld 3,000); SSA 20,000. Provisional = 30,000 + 10,000 = 40,000.
    # 6b = min(0.85*20,000, 0.5*9,000 + 0.85*(40,000-34,000)) = min(17,000, 9,600) = 9,600
    # 9 = 39,600; 12e = 15,750 + 2,000 = 17,750; 13b = 6,000 (AGI below 75,000)
    # 15 = 39,600 - 23,750 = 15,850; tax = 1,192.50 + 0.12*(15,850-11,925) = 1,663.50
    ex = {"d1": doc("W-2", box_1=30000, box_2=3000), "d2": doc("SSA-1099", box_5=20000)}
    c, _ = compute(view(extracted=ex))
    assert c["line_6b"]["value"] == 9600
    assert c["line_9"]["value"] == 39600 and c["line_11"]["value"] == 39600
    assert c["line_12e"]["value"] == 17750 and c["line_13b"]["value"] == 6000
    assert c["line_15"]["value"] == 15850 and c["line_16"]["value"] == 1663.5
    assert c["line_24"]["value"] == 1663.5 and c["line_33"]["value"] == 3000
    assert c["line_34"]["value"] == 1336.5 and c["line_37"]["value"] == 0


def test_amount_owed_when_payments_short():
    c, _ = compute(view(extracted={"d1": doc("W-2", box_1=30000, box_2=500)}))
    assert c["line_34"]["value"] == 0 and c["line_37"]["value"] > 0


def test_tools_called_in_dependency_order():
    _, calls = compute(view(extracted={"d1": doc("SSA-1099", box_5=10000)}))
    assert calls.index("calculate_taxable_social_security") < calls.index("calculate_standard_deduction")
    assert calls.index("calculate_taxable_social_security") < calls.index("calculate_senior_deduction")
    assert calls.index("calculate_senior_deduction") < calls.index("calculate_income_tax")


def test_line_6b_feeds_total_income():
    c, _ = compute(view(extracted={"d1": doc("SSA-1099", box_5=40000), "d2": doc("W-2", box_1=30000)}))
    assert c["line_9"]["inputs"]["line_6b"] == c["line_6b"]["value"] > 0
    assert c["line_9"]["value"] == 30000 + c["line_6b"]["value"]


def test_every_line_has_complete_provenance_and_direct_inputs_are_attributed():
    c, _ = compute(view(
        extracted={"d1": doc("W-2", box_1=20000, box_2=1000)},
        estimated_payments_amount=500, adjustments_amount=300, schedule2_part1_tax=50,
    ))
    assert all(KEYS <= set(r) for r in c.values())
    est = c["line_26"]
    assert est["tool"] == "make_direct_input_provenance"
    assert est["inputs"]["field_name"] == "estimated_payments_amount"
    assert est["inputs"]["entered_by"] and est["inputs"]["entered_on"]
    assert c["line_10"]["value"] == 300 and c["line_17"]["value"] == 50
    assert c["line_33"]["inputs"] == {"line_25a": 1000, "line_26": 500, "line_31": 0}
    assert c["line_1a"]["source"].startswith("Document d1")


def test_mfj_two_seniors_and_status_codes_from_rules():
    c, _ = compute(view(status="mfj", extracted={"d1": doc("W-2", box_1=50000)}, spouse_age=68))
    assert c["line_12e"]["value"] == 31500 + 1600 * 2
    assert c["line_13b"]["value"] == 12000


def test_missing_filing_status_fails_loudly():
    with pytest.raises(ValueError):
        compute({"facts": {}, "extracted": {}, "eligibility": {}})


def test_provenance_survives_the_graph_and_renders_clickable_form(tmp_path):
    graph = build_graph(trace_dir=tmp_path)
    result = graph.invoke(clean_case(), {"configurable": {"thread_id": "p5-e2e"}})
    computed = result["computed"]
    assert {"line_1a", "line_9", "line_16", "line_24", "line_33"} <= set(computed)
    assert all(KEYS <= set(r) for r in computed.values())
    html = render_draft_html(computed)
    assert html.count("<details>") == len(computed)
    assert "DRAFT" in html and "Formula:" in html and "Source:" in html


def test_form_refuses_amount_without_provenance():
    with pytest.raises(ValueError):
        render_draft_html({"line_9": {"value": 5}})


def test_real_intake_answer_names_are_understood():
    # docs/answer-names.md: birth date (not age), "yes"/"no" blindness, plain marital answers.
    v = {"facts": {k: {"value": x, "source": "user"} for k, x in {
        "married_dec31": "no", "household_situation": "single",
        "taxpayer_birth_date": "1950-03-04", "taxpayer_blind": "yes"}.items()},
        "extracted": {"d1": doc("W-2", box_1=20000)}, "eligibility": {}}
    c, _ = compute(v)
    assert c["line_12e"]["value"] == 15750 + 2000 * 2 and c["line_13b"]["value"] == 6000


def test_birth_date_cutoff_is_before_january_2_1961():
    base = {"married_dec31": "no", "household_situation": "single"}

    def senior_deduction(birth):
        facts = {k: {"value": x, "source": "user"} for k, x in {**base, "taxpayer_birth_date": birth}.items()}
        c, _ = compute({"facts": facts, "extracted": {}, "eligibility": {}})
        return c["line_13b"]["value"]
    assert senior_deduction("1961-01-01") == 6000 and senior_deduction("1961-01-02") == 0
