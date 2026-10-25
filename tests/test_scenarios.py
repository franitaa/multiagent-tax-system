"""The demo scenarios a teammate runs from the README must keep working."""
import sys

import pytest
from langgraph.types import Command

from src import state as S
from src.graph import build_graph
from src.scenarios import spouse_died_case
from scripts import run_scenarios
from tests.helpers import cfg


def test_spouse_died_pauses_then_finishes_with_the_human_supplied_filing_status(tmp_path):
    case, agents = spouse_died_case()
    graph = build_graph(trace_dir=tmp_path, agents=agents)

    paused = graph.invoke(case, cfg("eval2"))
    payload = paused["__interrupt__"][0].value
    assert payload["condition"] == S.FILING_STATUS_AMBIGUITY
    assert payload["options"] == ["continue", "stop"]
    assert payload["resolution_fields"] == ["filing_status"]
    assert "spouse" in payload["reason"]

    final = graph.invoke(Command(resume={
        "decision": "continue",
        "note": "volunteer confirmed the spouse died in the tax year",
        "resolution": {"filing_status": "married_filing_jointly"},
    }), cfg("eval2"))

    assert final["status"] == S.COMPLETE and final["review"]["verdict"] == "pass"
    assert final["facts"]["filing_status"] == {
        "value": "married_filing_jointly", "source": "human:FILING_STATUS_AMBIGUITY"}
    decision = final["human_decisions"][0]
    assert decision["decision"] == "continue" and decision["note"]
    assert decision["resolution"] == {"filing_status": "married_filing_jointly"}
    assert [e["to"] for e in final["handoff_log"]][:3] == ["intake", "human", "extraction"]


@pytest.mark.xfail(strict=True, reason=(
    "Rules (src/agents/rules.py) reads only facts['filing_status_claim'], so a volunteer's "
    "facts['filing_status'] never reaches the draft. Remove this marker once Rules reads "
    "facts['filing_status'] first (see docs/answer-names.md and docs/handoff-contract.md)."))
def test_the_human_supplied_filing_status_reaches_the_draft(tmp_path):
    case, agents = spouse_died_case()
    graph = build_graph(trace_dir=tmp_path, agents=agents)
    graph.invoke(case, cfg("eval2-flow"))
    final = graph.invoke(Command(resume={
        "decision": "continue", "note": "volunteer confirmed the spouse died in the tax year",
        "resolution": {"filing_status": "married_filing_jointly"},
    }), cfg("eval2-flow"))
    assert final["eligibility"]["filing_status"] == "married_filing_jointly"


def test_spouse_died_without_a_note_is_not_accepted(tmp_path):
    case, agents = spouse_died_case()
    graph = build_graph(trace_dir=tmp_path, agents=agents)
    graph.invoke(case, cfg("eval2-nonote"))
    again = graph.invoke(Command(resume={
        "decision": "continue", "note": " ", "resolution": {"filing_status": "single"}}), cfg("eval2-nonote"))
    assert "non-empty note" in again["__interrupt__"][0].value["error"]


@pytest.mark.parametrize("argv,expected", [
    (["clean"], "DRAFT READY"),
    (["interrupt"], "DRAFT READY"),
    (["interrupt", "--condition", "SOURCE_CONFLICT"], "DRAFT READY"),
    (["interrupt", "--condition", "OUT_OF_SCOPE"], "halted_by_human"),
    (["interrupt", "--condition", "EXPLOITATION_SIGNS"], "halted_by_human"),
    (["spouse-died"], "married_filing_jointly"),
    (["spouse-died", "--filing-status", "single"], "filing status: single (source: human:FILING_STATUS_AMBIGUITY)"),
    (["clean", "--no-context-strategy"], "DRAFT READY"),
])
def test_cli_scenarios_run_and_exit_zero(tmp_path, capsys, monkeypatch, argv, expected):
    monkeypatch.setattr(sys, "argv", ["run_scenarios", *argv, "--trace-dir", str(tmp_path)])
    assert run_scenarios.main() == 0
    assert expected in capsys.readouterr().out
    assert list(tmp_path.glob("*.jsonl")), "a trace must be written"
