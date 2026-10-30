"""ANSWER_UNCERTAIN for the scope-screening questions (asked by Supriya on #49).

The gate accepts a yes/no for each of the nine screening facts. Rules does not raise ANSWER_UNCERTAIN
for them yet (Matthew's change), so `rules_asking` stands in for it: it raises the condition for a
`not_sure` screening answer and otherwise runs the real Rules. What is tested here is the gate and
what the real Rules does with the volunteer's answer: "no" finishes the case, "yes" ends it as
OUT_OF_SCOPE, and anything else is refused.
"""
import pytest

from src import state as S
from src.agents import rules
from src.graph import build_graph
from src.orchestration import human
from src.scenarios import clean_case
from tests.helpers import cfg
from tests.test_answer_uncertain import JOINT, pending, volunteer

SCREENING = ("has_other_tax_forms", "sold_stocks_or_property", "business_or_rental_income",
             "foreign_income_or_accounts", "digital_assets", "can_be_claimed_as_dependent",
             "us_resident_all_year", "spouse_can_be_claimed", "spouse_itemizing")
MARRIED = {  # the two spouse questions are only read for these returns
    "spouse_can_be_claimed": JOINT,
    "spouse_itemizing": {"married_dec31": "yes", "file_jointly": "no", "spouse_birth_date": "1951-05-06"},
}
# the answer that takes the taxpayer out of scope
TRIGGER = {fact: "yes" for fact in SCREENING} | {"us_resident_all_year": "no"}
SAFE = {fact: "no" for fact in SCREENING} | {"us_resident_all_year": "yes"}


def rules_asking(view, tools):
    for fact in SCREENING:
        record = view["facts"].get(fact) or {}
        if record.get("value") == "not_sure":
            return {"eligibility": {}, "handoff_request": {"to": "human", "reason": S.ANSWER_UNCERTAIN},
                    "escalation": {"pending": True, "condition": S.ANSWER_UNCERTAIN, "raised_by": "rules",
                                   "reason": f"{fact} is not_sure; volunteer clarification required.",
                                   "fact": fact}}
    return rules.run(view, tools)


def intake_with(**answers):
    base = {"taxpayer_birth_date": "1950-03-04", "married_dec31": "no", "household_situation": "single"}
    facts = {k: {"value": v, "source": "user"} for k, v in {**base, **answers}.items()}
    return lambda view, tools: {"facts": facts, "pending_question": None, "intake_complete": True,
                                "handoff_request": {"to": "rules", "reason": "intake complete"}}


def start(tmp_path, fact):
    graph = build_graph(trace_dir=tmp_path, agents={
        "intake": intake_with(**MARRIED.get(fact, {}), **{fact: "not_sure"}), "rules": rules_asking})
    return graph, graph.invoke(clean_case(turns=1), cfg("t"))


def test_the_table_covers_the_nine_screening_facts_with_yes_and_no():
    assert all(human.UNCERTAIN_ANSWERS[fact] == ("yes", "no") for fact in SCREENING)


@pytest.mark.parametrize("fact", SCREENING)
def test_the_volunteer_is_asked_for_exactly_that_fact(tmp_path, fact):
    graph, result = start(tmp_path, fact)
    payload = pending(result)
    assert payload["condition"] == S.ANSWER_UNCERTAIN and payload["resolution_fields"] == [fact]
    assert payload["options"] == ["continue", "stop"]


@pytest.mark.parametrize("fact", SCREENING)
def test_a_no_lets_the_case_finish(tmp_path, fact):
    graph, _ = start(tmp_path, fact)
    final = volunteer(graph, {fact: SAFE[fact]})
    assert final["status"] == S.COMPLETE and final["eligibility"]["in_scope"] is True
    assert final["facts"][fact] == {"value": SAFE[fact], "source": "human:ANSWER_UNCERTAIN"}


@pytest.mark.parametrize("fact", SCREENING)
def test_a_yes_ends_the_case_as_out_of_scope(tmp_path, fact):
    graph, _ = start(tmp_path, fact)
    again = volunteer(graph, {fact: TRIGGER[fact]})
    payload = pending(again)
    assert payload["condition"] == S.OUT_OF_SCOPE and payload["options"] == ["stop"]
    assert graph.get_state(cfg("t")).values.get("status") != S.COMPLETE


@pytest.mark.parametrize("resolution", [
    {"digital_assets": "not_sure"}, {"digital_assets": "maybe"}, {"digital_assets": True},
    {"sold_stocks_or_property": "no"}, {"digital_assets": "no", "sold_stocks_or_property": "no"}, None,
], ids=["not-sure", "invalid", "bool", "wrong-fact", "extra-fact", "none"])
def test_a_bad_resolution_is_refused_and_nothing_is_overwritten(tmp_path, resolution):
    graph, _ = start(tmp_path, "digital_assets")
    again = volunteer(graph, resolution)
    assert "__interrupt__" in again and pending(again).get("error")
    assert graph.get_state(cfg("t")).values["facts"]["digital_assets"]["value"] == "not_sure"
