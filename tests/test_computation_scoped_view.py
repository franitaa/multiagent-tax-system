"""Computation must compute the same return whether or not the context strategy narrows its view.

The narrowed view once kept only numeric facts, which silently dropped the volunteer's
filing-status override, birth dates, blindness answers and the escalation flags."""
from src.agents import computation
from src.orchestration.access import ToolBox
from src.orchestration.context import view_for

FACTS = {
    "taxpayer_birth_date": "1950-03-04", "taxpayer_blind": "no", "spouse_birth_date": "1952-01-01",
    "spouse_blind": "no", "taxpayer_name": "Test Person", "has_dependents": "no",
    "filing_status": "married_filing_jointly",  # a volunteer's override
}


def state(**extra_facts):
    facts = {k: {"value": v, "source": "user"} for k, v in {**FACTS, **extra_facts}.items()}
    facts["filing_status"]["source"] = "human:FILING_STATUS_AMBIGUITY"
    return {
        "facts": facts, "eligibility": {"filing_status": "single", "in_scope": True},
        "extracted": {"d1": {"doc_id": "d1", "kind": "W-2", "fields": {"box_1": {"value": 40000.0}}}},
    }


def run(scoped, st):
    return computation.run(view_for("computation", st, scoped=scoped), ToolBox("computation"))


def test_scoped_and_full_views_compute_the_same_return():
    st = state()
    scoped, full = run(True, st)["computed"], run(False, st)["computed"]
    assert {k: v["value"] for k, v in scoped.items()} == {k: v["value"] for k, v in full.items()}


def test_the_volunteers_filing_status_override_reaches_computation():
    computed = run(True, state())["computed"]
    assert computed["line_12e"]["inputs"]["filing_status"] == "married_filing_jointly"
    assert computed["line_12e"]["value"] == 31500 + 2 * 1600  # both spouses 65+, joint


def test_free_text_facts_stay_out_of_the_computation_view():
    view = view_for("computation", state(), scoped=True)
    assert "taxpayer_name" not in view["facts"] and "has_dependents" not in view["facts"]


def test_the_dependent_flag_still_makes_computation_escalate_in_the_scoped_view():
    update = run(True, state(can_be_claimed_as_dependent="yes"))
    assert update["escalation"]["pending"] and update["handoff_request"]["to"] == "human"
