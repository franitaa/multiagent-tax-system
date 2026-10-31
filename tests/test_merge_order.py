"""Parallel extraction must give the same result whatever order the workers finish in."""
import itertools
import random
import threading
import time
from functools import reduce

import pytest
from langgraph.types import Command

from src import state as S
from src.agents import AGENTS
from src.graph import build_graph
from src.scenarios import clean_case, raising
from tests.helpers import cfg, read_trace

DOCS = [f"doc-{i}" for i in range(1, 5)]


def record(doc_id, value=1000.0):
    return {doc_id: {"doc_id": doc_id, "kind": "W-2", "fields": {"box_1": {"value": value, "source": doc_id}}}}


# ---- the reducers themselves ----------------------------------------------------------


def test_merge_extracted_all_permutations_of_four_documents():
    parts = [record(d, 1000.0 + i) for i, d in enumerate(DOCS)]
    results = [reduce(S.merge_extracted, perm, None) for perm in itertools.permutations(parts)]
    assert len(results) == 24
    assert all(r == results[0] for r in results)
    assert sorted(results[0]) == DOCS


def test_merge_extracted_is_associative():
    a, b, c, d = (record(x, i) for i, x in enumerate(DOCS))
    left = S.merge_extracted(S.merge_extracted(a, b), S.merge_extracted(c, d))
    right = S.merge_extracted(a, S.merge_extracted(b, S.merge_extracted(c, d)))
    assert left == right == reduce(S.merge_extracted, [d, c, b, a], None)


def test_merge_extracted_same_doc_twice_picks_the_same_winner_in_either_order():
    first, second = record("doc-1", 1.0), record("doc-1", 2.0)
    assert S.merge_extracted(first, second) == S.merge_extracted(second, first)


def test_merge_extracted_handles_empty_and_none():
    assert S.merge_extracted(None, None) == {}
    assert S.merge_extracted(record("doc-1"), {}) == record("doc-1")


def flags(*conditions):
    return [{"pending": True, "condition": c, "reason": f"r-{c}", "raised_by": "extraction"}
            for c in conditions]


def test_merge_escalation_keeps_every_flag_whatever_the_order():
    three = flags(S.TAX_ADVICE_REQUEST, S.FORM_1099R_BOX_2B, S.SOURCE_CONFLICT)
    results = [reduce(S.merge_escalation, perm, None) for perm in itertools.permutations(three)]
    assert all(r == results[0] for r in results)
    assert results[0]["condition"] == S.FORM_1099R_BOX_2B  # most severe first
    assert [q["condition"] for q in results[0]["queued"]] == [S.SOURCE_CONFLICT, S.TAX_ADVICE_REQUEST]


def test_merge_escalation_clear_and_replace():
    one, two = flags(S.SOURCE_CONFLICT, S.TAX_ADVICE_REQUEST)
    assert S.merge_escalation(one, None) is None
    assert S.merge_escalation(one, {**two, "replace": True}) == two  # human gate promotes next flag
    assert S.merge_escalation(None, one) == one


def test_merge_request_is_order_independent():
    a = {"from": "extraction", "to": "rules", "reason": "a"}
    b = {"from": "extraction", "to": "rules", "reason": "b"}
    assert S.merge_request(a, b) == S.merge_request(b, a)
    assert S.merge_request(a, None) is None  # the orchestrator's clear still works


# ---- the real parallel graph ----------------------------------------------------------


def delayed_extraction(delays, order, barrier=None):
    base = AGENTS["extraction"]

    def run(view, tools):
        doc_id = view["documents"][0]["id"]
        if barrier:
            barrier.wait(timeout=5)  # fails unless all workers are in flight at once
        time.sleep(delays[doc_id])
        update = base(view, tools)
        order.append(doc_id)
        return update

    return run


def run_parallel(tmp_path, delays, tid, barrier=True):
    order = []
    agents = {"extraction": delayed_extraction(delays, order, threading.Barrier(4) if barrier else None)}
    graph = build_graph(trace_dir=tmp_path, agents=agents)
    return graph.invoke(clean_case(n_docs=4), cfg(tid)), order


def test_workers_really_run_in_parallel_and_aggregate(tmp_path):
    result, order = run_parallel(tmp_path, {d: 0.0 for d in DOCS}, "par")  # barrier proves overlap
    assert result["status"] == S.COMPLETE and sorted(result["extracted"]) == DOCS
    assert sorted(order) == DOCS

    records = read_trace(tmp_path, "par")
    names = [r["agent"] for r in records]
    first = names.index("extraction")
    assert names[first:first + 5] == ["extraction"] * 4 + ["orchestrator"]  # fan-in: one orchestrator visit
    # scoped workers never read the conversation
    workers = [r for r in records if r["agent"] == "extraction"]
    assert all("messages" not in r["fields_read"] for r in workers)


def test_result_is_identical_for_opposite_completion_orders(tmp_path):
    forward, order_f = run_parallel(tmp_path, {d: 0.03 * i for i, d in enumerate(DOCS)}, "fwd")
    backward, order_b = run_parallel(tmp_path, {d: 0.03 * (3 - i) for i, d in enumerate(DOCS)}, "bwd")
    assert order_f != order_b, "test needs the workers to finish in different orders"
    assert forward["extracted"] == backward["extracted"]
    assert forward["handoff_log"] == backward["handoff_log"]


def test_result_is_identical_across_randomised_delays(tmp_path):
    rng = random.Random(1234)
    outcomes, orders = [], set()
    for run in range(12):
        delays = {d: rng.uniform(0, 0.03) for d in DOCS}
        result, order = run_parallel(tmp_path, delays, f"rnd{run}", barrier=False)
        outcomes.append(result["extracted"])
        orders.add(tuple(order))
    assert all(o == outcomes[0] for o in outcomes)
    assert len(orders) > 1, "randomised delays should have produced different completion orders"


def test_each_worker_gets_only_its_document_when_scoped_and_everything_when_not(tmp_path):
    seen = []

    def spy(view, tools):
        seen.append(view)
        return AGENTS["extraction"](view, tools)

    build_graph(trace_dir=tmp_path, agents={"extraction": spy}).invoke(clean_case(n_docs=4), cfg("s"))
    assert sorted(v["documents"][0]["id"] for v in seen) == DOCS
    assert all(len(v["documents"]) == 1 and "messages" not in v for v in seen)

    seen.clear()
    build_graph(trace_dir=tmp_path, context_strategy=False, agents={"extraction": spy}).invoke(
        clean_case(n_docs=4), cfg("u"))
    assert sorted(v["documents"][0]["id"] for v in seen) == DOCS
    assert all(len(v["documents"]) == 1 and "messages" in v for v in seen)


# ---- simultaneous escalations from parallel workers ------------------------------------


def two_flags():
    """doc-2's worker raises FILING_STATUS_AMBIGUITY and doc-3's raises SOURCE_CONFLICT."""
    only = lambda doc: (lambda view: view["documents"][0]["id"] == doc)
    inner = raising(AGENTS["extraction"], "extraction", S.SOURCE_CONFLICT, "TEST", only("doc-3"))
    return raising(inner, "extraction", S.FILING_STATUS_AMBIGUITY, "TEST", only("doc-2"))


def note(decision, text="checked (test)", **extra):
    return Command(resume={"decision": decision, "note": text, **extra})


@pytest.mark.parametrize("delays", [
    {d: 0.02 * i for i, d in enumerate(DOCS)},
    {d: 0.02 * (3 - i) for i, d in enumerate(DOCS)},
], ids=["doc-2 first", "doc-3 first"])
def test_two_simultaneous_flags_are_both_shown_to_a_human_in_a_fixed_order(tmp_path, delays):
    order = []
    inner = two_flags()

    def agent(view, tools):
        time.sleep(delays[view["documents"][0]["id"]])
        return inner(view, tools)

    graph = build_graph(trace_dir=tmp_path, agents={"extraction": agent})
    first = graph.invoke(clean_case(n_docs=4), cfg("two"))["__interrupt__"][0].value
    assert first["condition"] == S.FILING_STATUS_AMBIGUITY  # higher severity, whatever finished first
    assert first["also_pending"] == [S.SOURCE_CONFLICT]

    second = graph.invoke(note("continue", resolution={"filing_status": "single"}), cfg("two"))["__interrupt__"][0].value
    assert second["condition"] == S.SOURCE_CONFLICT and second["also_pending"] == []

    final = graph.invoke(note("continue"), cfg("two"))
    assert final["status"] == S.COMPLETE
    assert [d["condition"] for d in final["human_decisions"]] == [
        S.FILING_STATUS_AMBIGUITY, S.SOURCE_CONFLICT]
    assert final["human_decisions"][0]["also_raised"] == [S.SOURCE_CONFLICT]


def test_stop_on_the_first_flag_records_the_queued_one_in_the_audit_trail(tmp_path):
    graph = build_graph(trace_dir=tmp_path, agents={"extraction": two_flags()})
    graph.invoke(clean_case(n_docs=4), cfg("stop2"))
    final = graph.invoke(note("stop"), cfg("stop2"))
    assert final["status"] == S.HALTED_BY_HUMAN
    assert final["human_decisions"][0]["also_raised"] == [S.SOURCE_CONFLICT]
