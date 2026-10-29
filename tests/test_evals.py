"""The eval cases in evals/cases.json: well-formed, and every non-pending case passes."""
import pytest

from src import state as S
from evals import runner

CASES = runner.load_cases()
EXPECT_KEYS = {"interrupts", "status", "route_starts_with", "eligibility", "rules_include",
               "lines", "no_computed_lines", "review_verdict", "human_decisions"}
CASE_KEYS = {"id", "title", "messages", "facts", "documents", "resume", "expect", "pending"}


def test_case_ids_are_unique():
    ids = [c["id"] for c in CASES]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_case_is_well_formed(case):
    assert set(case) <= CASE_KEYS, set(case) - CASE_KEYS
    assert case["title"] and case["messages"] and case["expect"]
    assert set(case["expect"]) <= EXPECT_KEYS, set(case["expect"]) - EXPECT_KEYS
    for condition in case["expect"].get("interrupts", []):
        assert condition in S.ESCALATION_PRIORITY
    for doc in case.get("documents", []):
        assert {"id", "kind"} <= set(doc)
    if "status" in case["expect"]:
        assert case["expect"]["status"] in (S.COMPLETE, S.HALTED_BY_HUMAN)
    # every interrupt the case expects needs an answer to resume with
    assert len(case.get("resume", [])) >= len(case["expect"].get("interrupts", []))


@pytest.mark.parametrize("case", [
    pytest.param(c, marks=pytest.mark.xfail(reason=c["pending"])) if c.get("pending") else c
    for c in CASES
], ids=lambda c: c["id"])
def test_case_outcome(case, tmp_path):
    outcome = runner.run_case(case, trace_dir=tmp_path)
    assert runner.check(case, outcome) == []
    assert list(tmp_path.glob("*.jsonl")), "every eval run leaves a trace"


def test_a_pending_case_that_passes_is_reported_as_fixed(tmp_path):
    case = {**next(c for c in CASES if c["id"] == "eval-case-1-clean"), "pending": "test"}
    assert runner.evaluate(case, trace_dir=tmp_path)["result"] == runner.FIXED


def test_a_failing_case_makes_the_runner_exit_non_zero(monkeypatch, tmp_path):
    broken = {**CASES[0], "expect": {"status": S.HALTED_BY_HUMAN}}
    monkeypatch.setattr(runner, "load_cases", lambda: [broken])
    assert runner.main(["--trace-dir", str(tmp_path)]) == 1


def test_the_runner_exits_zero_when_only_pending_cases_fail(tmp_path, capsys):
    assert runner.main(["--trace-dir", str(tmp_path)]) == 0
    assert "0 fail" in capsys.readouterr().out
