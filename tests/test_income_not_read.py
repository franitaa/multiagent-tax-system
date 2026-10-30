"""INCOME_NOT_READ (#27): a draft must not finish with income left out and nobody told.

The taxpayer has an income form (said so in the interview, or uploaded it) but no amount from it reached the
return. Extraction reads W-2s only, so SSA-1099, 1099-INT and 1099-DIV are never read; a declared W-2 or 1099-R
may simply not have been uploaded. The orchestrator pauses the case before Computation, once, for a volunteer,
who can continue only with a note, or stop. Amounts are never invented: the lines stay zero and say NOT READ.
"""
import pytest
from langgraph.types import Command

from src import state as S
from src.graph import build_graph
from src.income_forms import forms_without_amounts
from src.orchestration.context import routing_view
from src.orchestration.router import route
from src.scenarios import clean_case, document
from tests.helpers import cfg


def fact(**answers):
    return {k: {"value": v, "source": "user"} for k, v in answers.items()}


def w2(**fields):
    return {"doc-1": {"doc_id": "doc-1", "kind": "W-2",
                      "fields": {k: {"value": v, "source": "doc-1"} for k, v in (fields or {"box_1": 1000.0}).items()}}}


def skipped(kind, doc_id="doc-2"):
    return {doc_id: {"doc_id": doc_id, "kind": kind, "fields": {}, "status": "skipped"}}


def intake_with(**answers):
    base = {"taxpayer_birth_date": "1950-03-04", "married_dec31": "no", "household_situation": "single"}
    facts = fact(**{**base, **answers})

    def intake(view, tools):
        return {"facts": facts, "pending_question": None, "intake_complete": True,
                "handoff_request": {"to": "extraction", "reason": "intake complete"}}
    return intake


def start(tmp_path, tid="t", documents=None, **answers):
    case = clean_case()
    if documents is not None:
        case["documents"] = documents
    graph = build_graph(trace_dir=tmp_path, agents={"intake": intake_with(**answers)})
    return graph, graph.invoke(case, cfg(tid))


def pending(result):
    return result["__interrupt__"][0].value


def resume(graph, tid="t", **answer):
    return graph.invoke(Command(resume=answer), cfg(tid))


# ---- which forms count ----------------------------------------------------------------------


def test_nothing_declared_and_nothing_uploaded_is_no_gap():
    assert forms_without_amounts({}, {}) == []


def test_a_declared_w2_with_no_upload_is_a_gap():
    assert forms_without_amounts(fact(has_w2="yes"), {}) == ["W-2"]


def test_a_declared_w2_with_its_amount_is_not():
    assert forms_without_amounts(fact(has_w2="yes"), w2()) == []
    assert forms_without_amounts(fact(has_w2="yes"), w2(box_1="1000.00")) == []  # text counts: Review handles it


def test_a_w2_with_no_wages_amount_is_a_gap():
    assert forms_without_amounts(fact(has_w2="yes"), w2(box_2=100.0)) == ["W-2"]


@pytest.mark.parametrize("kind, form, answer", [("SSA-1099", "SSA-1099", "has_ssa_1099"),
                                                ("1099-INT", "1099-INT", "has_1099_int"),
                                                ("1099-DIV", "1099-DIV", "has_1099_div")])
def test_the_forms_extraction_does_not_read_are_gaps_declared_or_uploaded(kind, form, answer):
    assert forms_without_amounts(fact(**{answer: "yes"}), {}) == [form]
    assert forms_without_amounts({}, skipped(kind)) == [form]


def test_a_declared_1099r_with_no_upload_is_a_gap():
    assert forms_without_amounts(fact(has_1099_r="yes"), {}) == ["1099-R"]
    uploaded = {"doc-3": {"doc_id": "doc-3", "kind": "1099-R", "fields": {}}}
    assert forms_without_amounts(fact(has_1099_r="yes"), uploaded) == []  # Extraction escalates box 2b itself


def test_no_and_not_sure_are_not_declarations():
    assert forms_without_amounts(fact(has_w2="no", has_ssa_1099="not_sure"), {}) == []


def test_the_names_come_in_a_fixed_order_and_a_fixed_vocabulary():
    everything = fact(has_w2="yes", has_ssa_1099="yes", has_1099_int="yes", has_1099_div="yes", has_1099_r="yes")
    assert forms_without_amounts(everything, {}) == ["W-2", "SSA-1099", "1099-INT", "1099-DIV", "1099-R"]


# ---- the routing view and the router --------------------------------------------------------------


def test_the_routing_view_carries_names_only():
    view = routing_view({"facts": fact(has_ssa_1099="yes"), "extracted": {}, "human_decisions": []})
    assert view["income_gaps"] == ["SSA-1099"]


def ready_view(**changes):
    view = {"n_messages": 2, "awaiting_since_msgs": None, "escalation": None, "done": False,
            "has_pending_question": False, "intake_complete": True, "n_docs_pending": 0, "has_eligibility": True,
            "in_scope": True, "eligibility_gaps": [], "has_computed": False, "review_verdict": None,
            "has_pending_revision": False, "revision_count": 0, "max_revisions": 3, "review_fail": None,
            "income_gaps": []}
    return {**view, **changes}


def test_a_gap_sends_the_case_to_a_human_before_computation():
    out = route(ready_view(income_gaps=["SSA-1099", "W-2"]))
    assert out.next == "human" and out.update["status"] == S.AWAITING_HUMAN
    esc = out.update["escalation"]
    assert esc["condition"] == S.INCOME_NOT_READ and esc["raised_by"] == "orchestrator" and esc["pending"]
    assert "SSA-1099, W-2" in esc["reason"]


def test_the_reason_says_that_continuing_does_not_add_the_amount():
    reason = route(ready_view(income_gaps=["SSA-1099"])).update["escalation"]["reason"]
    assert "does not add the amount" in reason and "$0" in reason


def test_the_escalation_names_the_forms_it_covers():
    assert route(ready_view(income_gaps=["W-2", "SSA-1099"])).update["escalation"]["forms"] == ["W-2", "SSA-1099"]


def decided(*forms, decision="continue"):
    entry = {"condition": S.INCOME_NOT_READ, "decision": decision, "note": "n", "resolution": None}
    return {**entry, "forms": list(forms)} if forms else entry


def test_a_volunteers_continue_covers_only_the_forms_it_named():
    state = {"facts": fact(has_w2="yes", has_ssa_1099="yes"), "extracted": {}, "human_decisions": [decided("W-2")]}
    assert routing_view(state)["income_gaps"] == ["SSA-1099"]  # a form that turns up later pauses again
    state["human_decisions"].append(decided("SSA-1099"))
    assert routing_view(state)["income_gaps"] == []


def test_a_decision_without_forms_covers_every_form():
    state = {"facts": fact(has_w2="yes", has_ssa_1099="yes"), "extracted": {}, "human_decisions": [decided()]}
    assert routing_view(state)["income_gaps"] == []


def test_a_stop_or_another_condition_does_not_cover_a_form():
    other = {"condition": S.TAX_ADVICE_REQUEST, "decision": "continue", "note": "n", "resolution": None}
    state = {"facts": fact(has_w2="yes"), "extracted": {}, "human_decisions": [decided("W-2", decision="stop"), other]}
    assert routing_view(state)["income_gaps"] == ["W-2"]


def test_no_gap_goes_straight_to_computation():
    assert route(ready_view()).next == "computation"


def test_out_of_scope_still_wins():
    out = route(ready_view(in_scope=False, income_gaps=["W-2"]))
    assert out.update["escalation"]["condition"] == S.OUT_OF_SCOPE


# ---- through the real graph -------------------------------------------------------------------------


def test_a_declared_w2_with_no_upload_pauses_instead_of_finishing_with_zero_wages(tmp_path):
    graph, result = start(tmp_path, documents=[], has_w2="yes")
    payload = pending(result)
    assert payload["condition"] == S.INCOME_NOT_READ and payload["raised_by"] == "orchestrator"
    assert payload["options"] == ["continue", "stop"] and "W-2" in payload["reason"]
    assert not graph.get_state(cfg("t")).values.get("computed"), "nothing is computed before the volunteer decides"


def test_continue_needs_a_note_and_no_resolution(tmp_path):
    graph, _ = start(tmp_path, documents=[], has_w2="yes")
    assert "note" in pending(resume(graph, decision="continue", note=""))["error"]
    again = resume(graph, decision="continue", note="added by hand", resolution={"line_1a": 100})
    assert "nothing to resolve" in pending(again)["error"]


def test_continue_with_a_note_finishes_once_and_is_not_asked_again(tmp_path):
    graph, _ = start(tmp_path, documents=[], has_w2="yes")
    final = resume(graph, decision="continue", note="W-2 amounts added by hand")
    assert "__interrupt__" not in final and final["status"] == S.COMPLETE
    decisions = [d for d in final["human_decisions"] if d["condition"] == S.INCOME_NOT_READ]
    assert len(decisions) == 1 and decisions[0]["note"] == "W-2 amounts added by hand"
    assert decisions[0]["forms"] == ["W-2"]  # the router pauses again only for a form this did not cover
    assert final["computed"]["line_1a"]["value"] == 0  # nothing invented


def test_stop_ends_the_case(tmp_path):
    graph, _ = start(tmp_path, documents=[], has_w2="yes")
    final = resume(graph, decision="stop", note="")
    assert final["status"] == S.HALTED_BY_HUMAN and not final.get("computed")


def test_a_skipped_form_pauses_and_the_draft_still_warns_after_continue(tmp_path):
    from src.draft_form import write_draft_form

    graph, result = start(tmp_path, documents=[document("doc-1", "W-2"), document("doc-2", "SSA-1099")],
                          has_w2="yes", has_ssa_1099="yes")
    assert pending(result)["condition"] == S.INCOME_NOT_READ and "SSA-1099" in pending(result)["reason"]
    final = resume(graph, decision="continue", note="amount added by hand")
    page = write_draft_form(final, tmp_path / "out", "t").read_text(encoding="utf-8")
    assert "Income is missing from this draft" in page


def test_a_case_with_its_documents_is_not_paused(tmp_path):
    graph, result = start(tmp_path, documents=[document("doc-1", "W-2")], has_w2="yes")
    assert "__interrupt__" not in result and result["status"] == S.COMPLETE


def test_a_case_that_declares_nothing_is_not_paused(tmp_path):
    _, result = start(tmp_path, documents=[], has_w2="no")
    assert "__interrupt__" not in result and result["status"] == S.COMPLETE


def test_a_form_that_turns_up_after_the_pause_pauses_the_case_again(tmp_path):
    graph, _ = start(tmp_path, documents=[], has_w2="yes")
    graph.update_state(cfg("t"), {"facts": fact(has_ssa_1099="yes")})  # a corrected answer while it waited
    again = resume(graph, decision="continue", note="W-2 handled by hand")
    assert pending(again)["condition"] == S.INCOME_NOT_READ
    assert "SSA-1099" in pending(again)["reason"] and "W-2" not in pending(again)["reason"]
    final = resume(graph, decision="continue", note="SSA-1099 handled by hand")
    assert "__interrupt__" not in final and final["status"] == S.COMPLETE


# ---- the draft form also warns for a declared W-2 or 1099-R that was never added ----------------
# (found in the demo rehearsal: after "I don't have it now" the draft showed wages of $0 with no warning)


def test_the_missing_income_list_names_the_forms_and_their_lines():
    from src.income_forms import missing_income_forms

    facts = {"has_w2": {"value": "yes"}, "has_1099_r": {"value": "yes"}}
    assert missing_income_forms(facts, {}) == [
        {"form": "W-2", "lines": ["line_1a", "line_25a"]},
        {"form": "1099-R", "lines": ["line_4a", "line_4b", "line_5a", "line_5b", "line_25b"]}]
    assert [f["form"] for f in missing_income_forms(facts, {})] == forms_without_amounts(facts, {})


def test_a_w2_never_added_leaves_a_draft_that_warns_after_continue(tmp_path):
    from src.draft_form import write_draft_form

    graph, result = start(tmp_path, documents=[], has_w2="yes")
    assert pending(result)["condition"] == S.INCOME_NOT_READ
    final = resume(graph, decision="continue", note="taxpayer will bring the W-2 later")
    assert final["status"] == S.COMPLETE and final["computed"]["line_1a"]["value"] == 0
    page = write_draft_form(final, tmp_path / "out", "t").read_text(encoding="utf-8")
    assert "Income is missing from this draft" in page and "W-2: feeds lines 1a, 25a" in page


def test_a_w2_that_was_added_leaves_no_warning(tmp_path):
    from src.draft_form import write_draft_form

    graph, result = start(tmp_path, documents=[document("doc-1", "W-2")], has_w2="yes")
    page = write_draft_form(result, tmp_path / "out", "t").read_text(encoding="utf-8")
    assert "Income is missing" not in page
