"""Review/Audit agent: it must pass a correct return and catch every way of breaking one.

The fixture is a correct single-filer return (age 70) with a W-2, an SSA-1099, a 1099-INT
and a pension 1099-R, built with the same tax_math tools Computation uses. Each test breaks
one thing and checks that Review fails it with the right check, without fixing anything.
"""
import copy
import inspect

import pytest
from langgraph.types import Command

import tax_math
from src import state as S
from src.agents import AGENTS, review
from src.graph import build_graph
from src.orchestration.access import ToolBox
from src.scenarios import clean_case
from tests.helpers import cfg

FS = "single"


def rec(value, inputs, tool="sum_tool", formula="sum", source="computed"):
    return {"value": value, "formula": formula, "inputs": inputs, "source": source, "tool": tool}


def doc(kind, **fields):
    return {"kind": kind, "fields": {k: {"value": v} for k, v in fields.items()}}


def correct_view():
    extracted = {
        "w2-1": doc("W-2", box_1=20000.0, box_2=1500.0),
        "ssa-1": doc("SSA-1099", box_5=24000.0),
        "int-1": doc("1099-INT", box_1=500.0, box_8=200.0),
        "r-1": doc("1099-R", box_1=10000.0, box_2a=10000.0, box_4=1000.0, box_7="7"),
    }
    c = {}
    c["line_1a"] = rec(20000.0, {"w2-1.box_1": 20000.0})
    c["line_1z"] = rec(20000.0, {"line_1a": 20000.0})
    c["line_2a"] = rec(200.0, {"int-1.box_8": 200.0})
    c["line_2b"] = rec(500.0, {"int-1.box_1": 500.0})
    c["line_5a"] = rec(10000.0, {"r-1.box_1": 10000.0})
    c["line_5b"] = rec(10000.0, {"r-1.box_2a": 10000.0})
    c["line_6a"] = rec(24000.0, {"ssa-1.box_5": 24000.0})
    other = 20000.0 + 500.0 + 10000.0
    c["line_6b"] = tax_math.calculate_taxable_social_security(24000.0, other, 200.0, FS)
    line_9 = other + c["line_6b"]["value"]
    c["line_9"] = rec(line_9, {"line_1z": 20000.0, "line_6b": c["line_6b"]["value"]})
    c["line_11a"] = rec(line_9, {"line_9": line_9})
    c["line_12e"] = tax_math.calculate_standard_deduction(FS, age_65_or_older=True)
    c["line_13b"] = tax_math.calculate_senior_deduction(line_9, 1, FS)
    line_14 = c["line_12e"]["value"] + c["line_13b"]["value"]
    c["line_14"] = rec(line_14, {"line_12e": c["line_12e"]["value"], "line_13b": c["line_13b"]["value"]})
    line_15 = max(0.0, line_9 - line_14)
    c["line_15"] = rec(line_15, {"line_11a": line_9, "line_14": line_14})
    c["line_16"] = tax_math.calculate_income_tax(line_15, FS)
    tax = c["line_16"]["value"]
    c["line_24"] = rec(tax, {"line_16": tax})
    c["line_25a"] = rec(1500.0, {"w2-1.box_2": 1500.0})
    c["line_25b"] = rec(1000.0, {"r-1.box_4": 1000.0})
    c["line_25d"] = rec(2500.0, {"line_25a": 1500.0, "line_25b": 1000.0})
    c["line_33"] = rec(2500.0, {"line_25d": 2500.0})
    c["line_34"] = rec(max(0.0, 2500.0 - tax), {"line_33": 2500.0, "line_24": tax})
    c["line_37"] = rec(max(0.0, tax - 2500.0), {"line_24": tax, "line_33": 2500.0})
    eligibility = {
        "in_scope": True, "eligible_1040sr": True, "filing_status": FS,
        "taxpayer_qualifies": True, "spouse_qualifies": None, "age_blindness_boxes": 1,
    }
    facts = {"age": {"value": 70, "source": "user"}}
    return {"computed": c, "extracted": extracted, "eligibility": eligibility, "facts": facts}


def tools():
    return ToolBox("review")


def run_review(view):
    return review.run(view, tools())


def errors(update, check=None):
    return [f for f in update["review"]["findings"]
            if f["severity"] == "error" and (check is None or f["check"] == check)]


def failed_on(view, check, line=None):
    update = run_review(view)
    assert update["review"]["verdict"] == "fail"
    assert update["review"]["send_back_to"] == "computation"
    hits = [f for f in errors(update, check) if line is None or f["line"] == line]
    assert hits, f"expected a {check} error on {line}, got {update['review']['findings']}"
    return hits


def set_value(view, line, value):
    view["computed"][line]["value"] = value


# ---- a correct return passes ----------------------------------------------------------


def test_correct_return_passes_with_no_findings():
    update = run_review(correct_view())
    assert update["review"] == {"verdict": "pass", "findings": [], "send_back_to": None}
    assert update["handoff_request"]["to"] == "end"
    assert "escalation" not in update


def test_the_fixture_exercises_the_social_security_worksheet():
    view = correct_view()
    assert 0 < view["computed"]["line_6b"]["value"] < view["computed"]["line_6a"]["value"]


def test_review_never_modifies_the_return():
    view = correct_view()
    set_value(view, "line_9", 1.0)
    before = copy.deepcopy(view)
    update = run_review(view)
    assert view == before
    assert set(update) <= {"review", "handoff_request", "escalation"}


def test_review_recomputes_through_its_toolbox():
    box = tools()
    review.run(correct_view(), box)
    assert set(box.calls) == set(review.TOOL_LINES.values())


@pytest.mark.parametrize("tool", sorted(review.TOOL_PARAMS))
def test_tool_parameters_match_tax_math(tool):
    params = tuple(inspect.signature(getattr(tax_math, tool)).parameters)
    assert params == review.TOOL_PARAMS[tool]


# ---- provenance ----------------------------------------------------------------------


@pytest.mark.parametrize("key", ["formula", "inputs", "source", "tool"])
def test_missing_provenance_field_fails(key):
    view = correct_view()
    del view["computed"]["line_2b"][key]
    failed_on(view, "provenance", "line_2b")


def test_a_bare_number_without_provenance_fails():
    view = correct_view()
    view["computed"]["line_2b"] = 500.0
    failed_on(view, "provenance", "line_2b")


def test_non_numeric_value_fails():
    view = correct_view()
    set_value(view, "line_2b", "about 500")
    failed_on(view, "provenance", "line_2b")


def test_direct_user_input_needs_who_and_when():
    view = correct_view()
    view["computed"]["line_26"] = rec(0.0, {}, tool="intake", source=review.DIRECT_INPUT)
    failed_on(view, "provenance", "line_26")


def test_recorded_direct_user_input_is_accepted():
    view = correct_view()
    view["computed"]["line_26"] = rec(
        0.0, {"entered_by": "taxpayer", "entered_on": "2026-10-26"}, tool="intake",
        source=review.DIRECT_INPUT)
    assert run_review(view)["review"]["verdict"] == "pass"


def test_who_and_when_may_sit_next_to_the_value_as_in_answer_names():
    view = correct_view()
    view["computed"]["line_26"] = {
        **rec(0.0, {}, tool="intake", source="Direct user input"),
        "entered_by": "taxpayer", "entered_on": "2026-10-26"}
    assert run_review(view)["review"]["verdict"] == "pass"


@pytest.mark.parametrize("answer,boxes_add", [("yes", 2000), ("no", 0), ("not_sure", 0)])
def test_blindness_answers_are_read_as_yes_no_not_sure(answer, boxes_add):
    view = correct_view()
    view["facts"]["taxpayer_blind"] = {"value": answer, "source": "user"}
    view["computed"]["line_12e"] = tax_math.calculate_standard_deduction(
        FS, age_65_or_older=True, blind=boxes_add > 0)
    hits = [f for f in errors(run_review(view), "recompute") if f["line"] == "line_12e"]
    assert hits == []


def test_a_line_nobody_can_verify_fails():
    view = correct_view()
    view["computed"]["line_8"] = rec(0.0, {}, tool="mystery")
    failed_on(view, "completeness", "line_8")


# ---- sources -------------------------------------------------------------------------


def test_line_disagreeing_with_the_w2_fails():
    view = correct_view()
    view["extracted"]["w2-1"]["fields"]["box_1"]["value"] = 21000.0
    failed_on(view, "sources", "line_1a")


def test_line_not_equal_to_its_cited_documents_fails():
    view = correct_view()
    set_value(view, "line_2b", 600.0)
    failed_on(view, "sources", "line_2b")


def test_citing_a_document_that_was_not_extracted_fails():
    view = correct_view()
    view["computed"]["line_1a"]["inputs"] = {"w2-9.box_1": 20000.0}
    failed_on(view, "sources", "line_1a")


def test_dropped_document_amount_fails():
    view = correct_view()
    view["extracted"]["w2-2"] = doc("W-2", box_1=5000.0)  # second W-2 never reaches line 1a
    hits = failed_on(view, "sources", "line_1a")
    assert any("w2-2" in f["issue"] for f in hits)


def test_dropped_withholding_fails():
    view = correct_view()
    del view["computed"]["line_25b"]
    failed_on(view, "sources", "line_25b")


def test_stale_line_reference_fails():
    view = correct_view()
    view["computed"]["line_14"]["inputs"]["line_12e"] = 15750  # value before the age box
    failed_on(view, "sources", "line_14")


# ---- independent recomputation -------------------------------------------------------


def test_tool_value_that_does_not_match_its_own_inputs_fails():
    view = correct_view()
    set_value(view, "line_12e", 15750)  # record still says age_65_or_older=True
    hits = failed_on(view, "recompute", "line_12e")
    assert any("own inputs" in f["issue"] for f in hits)


def test_standard_deduction_missing_the_age_box_fails():
    view = correct_view()
    view["computed"]["line_12e"] = tax_math.calculate_standard_deduction(FS, age_65_or_older=False)
    hits = failed_on(view, "recompute", "line_12e")
    assert any("age_65_or_older" in f["issue"] for f in hits)


def test_social_security_computed_before_the_rest_of_income_fails():
    """Ordering dependency: 6b needs all other income. Here the pension was left out."""
    view = correct_view()
    c = view["computed"]
    early = tax_math.calculate_taxable_social_security(24000.0, 20500.0, 200.0, FS)
    c["line_6b"] = early
    line_9 = 30500.0 + early["value"]
    c["line_9"]["value"] = c["line_11a"]["value"] = line_9
    failed_on(view, "recompute", "line_6b")


def test_senior_deduction_on_the_wrong_magi_fails():
    view = correct_view()
    view["computed"]["line_13b"] = tax_math.calculate_senior_deduction(200000.0, 1, FS)
    failed_on(view, "recompute", "line_13b")


def test_tool_line_produced_by_another_tool_fails():
    view = correct_view()
    view["computed"]["line_16"]["tool"] = "sum_tool"
    failed_on(view, "recompute", "line_16")


def test_tool_run_on_a_different_filing_status_fails():
    view = correct_view()
    view["computed"]["line_16"] = tax_math.calculate_income_tax(
        view["computed"]["line_15"]["value"], "head_of_household")
    hits = failed_on(view, "recompute", "line_16")
    assert any("filing status" in f["issue"] for f in hits)


def test_short_filing_status_codes_from_rules_are_understood():
    view = correct_view()
    view["eligibility"]["filing_status"] = "SINGLE "
    assert run_review(view)["review"]["verdict"] == "pass"


def test_qualified_dividends_only_warn_about_the_rate_schedule():
    view = correct_view()
    view["extracted"]["div-1"] = doc("1099-DIV", box_1a=0.0, box_1b=0.0)
    view["computed"]["line_3a"] = rec(100.0, {"line_3b": 100.0})
    update = run_review(view)
    warnings = [f for f in update["review"]["findings"] if f["severity"] == "warning"]
    assert any(f["line"] == "line_16" for f in warnings)


# ---- totals --------------------------------------------------------------------------


@pytest.mark.parametrize("line", [
    "line_1z", "line_9", "line_11a", "line_14", "line_15", "line_24", "line_25d", "line_33",
    "line_34", "line_37",
])
def test_every_total_is_recomputed(line):
    view = correct_view()
    set_value(view, line, view["computed"][line]["value"] + 100.0)
    failed_on(view, "totals", line)


def test_rounding_to_whole_dollars_is_tolerated():
    view = correct_view()
    c = view["computed"]
    tax = round(c["line_16"]["value"])
    c["line_16"]["value"] = c["line_24"]["value"] = tax
    c["line_24"]["inputs"]["line_16"] = tax
    c["line_34"]["value"] = max(0.0, 2500.0 - tax)
    c["line_34"]["inputs"]["line_24"] = c["line_37"]["inputs"]["line_24"] = tax
    assert run_review(view)["review"]["verdict"] == "pass"


# ---- internal contradictions ---------------------------------------------------------


def test_taxable_social_security_above_benefits_fails():
    view = correct_view()
    set_value(view, "line_6b", 30000.0)
    hits = failed_on(view, "contradictions", "line_6b")
    assert any("exceeds total benefits" in f["issue"] for f in hits)


def test_taxable_social_security_above_85_percent_fails():
    view = correct_view()
    set_value(view, "line_6b", 0.9 * 24000.0)
    failed_on(view, "contradictions", "line_6b")


def test_taxable_pension_above_total_fails():
    view = correct_view()
    set_value(view, "line_5b", 12000.0)
    failed_on(view, "contradictions", "line_5b")


def test_negative_amount_fails():
    view = correct_view()
    set_value(view, "line_2b", -500.0)
    failed_on(view, "contradictions", "line_2b")


def test_overpaid_and_owing_at_once_fails():
    view = correct_view()
    set_value(view, "line_34", 10.0)
    set_value(view, "line_37", 10.0)
    failed_on(view, "contradictions", "line_34")


# ---- completeness --------------------------------------------------------------------


@pytest.mark.parametrize("line", ["line_16", "line_6b", "line_13b", "line_1z"])
def test_required_line_missing_fails(line):
    view = correct_view()
    del view["computed"][line]
    failed_on(view, "completeness", line)


def test_empty_return_fails():
    view = correct_view()
    view["computed"] = {}
    failed_on(view, "completeness")


# ---- nothing out of scope slipped through --------------------------------------------


def escalated(view, condition):
    update = run_review(view)
    assert update["review"]["verdict"] == "fail"
    assert update["escalation"]["condition"] == condition
    assert update["escalation"]["raised_by"] == "review"
    assert update["handoff_request"]["to"] == "human"
    return update


def test_out_of_scope_document_escalates():
    view = correct_view()
    view["extracted"]["nec-1"] = doc("1099-NEC", box_1=3000.0)
    escalated(view, S.OUT_OF_SCOPE)


def test_1099r_with_box_2b_escalates():
    view = correct_view()
    view["extracted"]["r-1"]["fields"]["box_2b"] = {"value": True}
    escalated(view, S.FORM_1099R_BOX_2B)


def test_most_severe_scope_problem_is_raised():
    view = correct_view()
    view["extracted"]["r-1"]["fields"]["box_2b"] = {"value": True}
    view["extracted"]["nec-1"] = doc("1099-NEC", box_1=3000.0)
    update = escalated(view, S.OUT_OF_SCOPE)
    assert "FORM_1099R_BOX_2B" in update["escalation"]["reason"]


@pytest.mark.parametrize("change", [
    {"in_scope": False}, {"in_scope": None}, {"eligible_1040sr": False},
])
def test_eligibility_not_clean_escalates(change):
    view = correct_view()
    view["eligibility"].update(change)
    escalated(view, S.OUT_OF_SCOPE)


@pytest.mark.parametrize("line", ["schedule_c_net_profit", "line_7"])
def test_out_of_scope_line_escalates(line):
    view = correct_view()
    view["computed"][line] = rec(1000.0, {"entered_by": "taxpayer", "entered_on": "2026-10-26"},
                                 tool="intake", source=review.DIRECT_INPUT)
    escalated(view, S.OUT_OF_SCOPE)


def test_eligibility_ignoring_the_volunteers_filing_status_fails():
    view = correct_view()
    view["facts"]["filing_status"] = {"value": "head_of_household",
                                      "source": "human:FILING_STATUS_AMBIGUITY"}
    failed_on(view, "scope")


def test_escalation_reason_carries_no_document_details():
    view = correct_view()
    view["extracted"]["nec-1"] = doc("1099-NEC", box_1=3000.0)
    reason = run_review(view)["escalation"]["reason"]
    assert "nec-1" not in reason and "3000" not in reason


# ---- bounded output ------------------------------------------------------------------


def test_findings_are_bounded_and_errors_come_first():
    view = correct_view()
    for line in list(view["computed"]):
        view["computed"][line]["value"] = -1.0
    view["computed"]["line_3a"] = rec(100.0, {"line_3b": 100.0})
    findings = run_review(view)["review"]["findings"]
    assert len(findings) == review.MAX_FINDINGS
    assert "more findings" in findings[-1]["issue"]
    assert all(f["severity"] == "error" for f in findings)


# ---- in the graph: the review -> revise loop with the real Review agent --------------


def consistent_computation(view, tools):
    """Test-only Computation: a small, correct draft for the stub W-2s (box 1 only, single,
    65+), so these tests do not depend on the Computation teammate's stub."""
    eligibility = view.get("eligibility", {})
    wages = {f"{doc_id}.box_1": record["fields"]["box_1"]["value"]
             for doc_id, record in sorted(view.get("extracted", {}).items())}
    total = sum(wages.values())
    c = {
        "line_1a": rec(total, wages),
        "line_1z": rec(total, {"line_1a": total}),
        "line_9": rec(total, {"line_1z": total}),
        "line_11a": rec(total, {"line_9": total}),
        "line_12e": tools.call("calculate_standard_deduction", filing_status=FS,
                               age_65_or_older=eligibility.get("taxpayer_qualifies") is True),
        "line_13b": tools.call("calculate_senior_deduction", magi=total, qualifying_people=1,
                               filing_status=FS),
    }
    deductions = c["line_12e"]["value"] + c["line_13b"]["value"]
    taxable = max(0.0, total - deductions)
    c["line_14"] = rec(deductions, {})
    c["line_15"] = rec(taxable, {})
    c["line_16"] = tools.call("calculate_income_tax", taxable_income=taxable, filing_status=FS)
    tax = c["line_16"]["value"]
    c["line_24"] = rec(tax, {})
    c["line_33"] = rec(0.0, {})
    c["line_34"] = rec(0.0, {})
    c["line_37"] = rec(tax, {})
    return {"computed": c}


def test_the_teammates_computation_stub_is_rejected(tmp_path):
    """Until the real Computation lands, Review fails the one-line stub and the loop ends
    with a human, as it should."""
    graph = build_graph(trace_dir=tmp_path)
    result = graph.invoke(clean_case(), cfg("stub"))
    assert result["__interrupt__"][0].value["condition"] == S.REVIEW_BOUND_EXCEEDED
    findings = graph.get_state(cfg("stub")).values["review_history"][0]["findings"]
    assert any(f["check"] == "completeness" for f in findings)


def broken_then_fixed(times_broken):
    """Computation that inflates line 9 for its first `times_broken` calls."""
    calls = []

    def computation(view, tools):
        calls.append(view.get("pending_revision"))
        update = consistent_computation(view, tools)
        if len(calls) <= times_broken:
            update["computed"]["line_9"] = {**update["computed"]["line_9"], "value": 999999.0}
        return update

    return computation, calls


def test_real_review_sends_a_wrong_line_back_and_then_passes(tmp_path):
    computation, calls = broken_then_fixed(1)
    graph = build_graph(trace_dir=tmp_path, agents={"computation": computation})
    result = graph.invoke(clean_case(), cfg("fix"))
    assert result["status"] == S.COMPLETE and result["review"]["verdict"] == "pass"
    assert result["revision_count"] == 1
    assert calls[0] is None
    assert any(f["line"] == "line_9" and f["check"] == "totals" for f in calls[1]["findings"])


def test_real_review_that_keeps_failing_hits_the_bound(tmp_path):
    computation, calls = broken_then_fixed(100)
    graph = build_graph(trace_dir=tmp_path, agents={"computation": computation})
    result = graph.invoke(clean_case(), cfg("bound"))
    assert result["__interrupt__"][0].value["condition"] == S.REVIEW_BOUND_EXCEEDED
    assert len(calls) == S.DEFAULT_MAX_REVISIONS + 1


def test_out_of_scope_document_rules_missed_is_caught_by_review(tmp_path):
    def extraction(view, tools):
        update = AGENTS["extraction"](view, tools)
        for record in update["extracted"].values():
            record["kind"] = "1099-NEC"
        return update

    graph = build_graph(trace_dir=tmp_path, agents={"extraction": extraction,
                                                    "computation": consistent_computation})
    result = graph.invoke(clean_case(), cfg("nec"))
    payload = result["__interrupt__"][0].value
    assert payload["condition"] == S.OUT_OF_SCOPE and payload["raised_by"] == "review"
    assert payload["options"] == ["stop"]
    final = graph.invoke(Command(resume={"decision": "stop", "note": "Schedule C client"}), cfg("nec"))
    assert final["status"] == S.HALTED_BY_HUMAN
