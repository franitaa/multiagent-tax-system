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
    assert c["line_9"]["value"] == 39600 and c["line_11a"]["value"] == 39600
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
    assert c["line_33"]["inputs"] == {"line_25d": 1000, "line_26": 500, "line_31": 0}
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


def test_spec_line_ids_a_and_b_pairs_and_withholding_split():
    ex = {
        "w": doc("W-2", box_1=20000, box_2=1500),
        "i": doc("1099-INT", box_1=300, box_8=200, box_4=10),
        "dv": doc("1099-DIV", box_1a=400, box_1b=250),
        "ira": doc("1099-R", box_1=5000, box_2a=4000, box_4=100, ira_sep_simple=True),
        "pen": doc("1099-R", box_1=9000, box_2a=8000, box_4=200),
    }
    c, _ = compute(view(extracted=ex))
    assert (c["line_1z"]["value"], c["line_2a"]["value"], c["line_2b"]["value"]) == (20000, 200, 300)
    assert (c["line_3a"]["value"], c["line_3b"]["value"]) == (250, 400)
    assert (c["line_4a"]["value"], c["line_4b"]["value"]) == (5000, 4000)
    assert (c["line_5a"]["value"], c["line_5b"]["value"]) == (9000, 8000)
    assert c["line_9"]["value"] == 20000 + 300 + 400 + 4000 + 8000
    assert c["line_25b"]["value"] == 310 and c["line_25d"]["value"] == 1810
    assert c["line_25d"]["inputs"] == {"line_25a": 1500, "line_25b": 310, "line_25c": 0}
    assert c["line_25c"]["value"] == 0 and "No other withholding forms" in c["line_25c"]["source"]


def test_tax_exempt_interest_raises_provisional_income_for_6b():
    base = {"d": doc("SSA-1099", box_5=20000), "w": doc("W-2", box_1=20000)}
    low, _ = compute(view(extracted=base))
    high, _ = compute(view(extracted={**base, "i": doc("1099-INT", box_1=0, box_8=8000)}))
    assert high["line_6b"]["inputs"]["tax_exempt_interest"] == 8000
    assert high["line_6b"]["value"] > low["line_6b"]["value"]


def escalates(v, condition):
    update = computation.run(v, ToolBox("computation"))
    assert update["escalation"]["condition"] == condition and "computed" not in update
    assert update["handoff_request"]["to"] == "human"


def test_defensive_escalations():
    from src.state import FORM_1099R_BOX_2B, OUT_OF_SCOPE
    escalates(view(extracted={"r": doc("1099-R", box_1=900, box_2a=0, box_2b=True)}), FORM_1099R_BOX_2B)
    escalates(view(extracted={"r": doc("1099-R", box_1=900)}), FORM_1099R_BOX_2B)  # taxable amount missing
    escalates(view(extracted={"n": doc("1099-NEC", box_1=500)}), OUT_OF_SCOPE)
    escalates(view(can_be_claimed_as_dependent="yes"), OUT_OF_SCOPE)
    escalates(view(status="mfs", spouse_itemizing="yes"), OUT_OF_SCOPE)


def test_spouse_itemizing_only_matters_when_filing_separately():
    c, _ = compute(view(status="mfj", spouse_itemizing="yes", extracted={"w": doc("W-2", box_1=1000)}))
    assert c["line_12e"]["value"] >= 31500


def test_resolved_condition_is_not_raised_again():
    v = view(can_be_claimed_as_dependent="yes", extracted={"w": doc("W-2", box_1=1000)})
    v["human_decisions"] = [{"condition": "OUT_OF_SCOPE", "decision": "continue"}]
    assert "computed" in computation.run(v, ToolBox("computation"))


def test_form_shows_status_boxes_and_masked_valid_test_ssns_only():
    c, _ = compute(view(extracted={"w": doc("W-2", box_1=1000)}))
    facts = {"dependents": {"value": [
        {"name": "Alex", "relationship": "grandchild", "ssn": "912-34-5678"},
        {"name": "Sam", "relationship": "grandchild", "ssn": "123-45-6789"}], "source": "user"}}
    html = render_draft_html(c, facts, {"filing_status": "mfj", "age_blindness_boxes": 2})
    assert "Married filing jointly" in html and "Line 12d: age and blindness boxes" in html
    assert "XXX-XX-5678" in html and "912-34-5678" not in html
    assert "123-45-6789" not in html and "[not a valid test SSN]" in html
    assert "<th scope='row'>1z</th>" in html and "<th scope='row'>11a</th>" in html


def test_tools_are_served_over_mcp_and_match_direct_calls():
    import asyncio
    pytest.importorskip("mcp.server.mcpserver")
    from src.tax_math_mcp import server
    from tax_math import calculate_income_tax

    async def go():
        tools = {t.name for t in await server.list_tools()}
        result = await server.call_tool(
            "calculate_income_tax", {"taxable_income": 20000, "filing_status": "single"})
        return tools, result

    tools, result = asyncio.run(go())
    assert {"calculate_income_tax", "calculate_taxable_social_security",
            "calculate_senior_deduction", "calculate_standard_deduction"} <= tools
    expected = calculate_income_tax(20000, "single")["value"]
    assert str(expected) in str(result)
