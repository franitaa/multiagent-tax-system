"""Telemetry: the numbers the dashboard shows, from traces made by the real graph.

Each test runs a scenario with `trace_dir=tmp_path` and reads the result back with src/telemetry.py, so
the tests follow the runner as it changes. Nothing here depends on a browser.
"""
import json
from pathlib import Path

import pytest
from langgraph.types import Command

from src import state as S
from src import telemetry as T
from src.audit import AuditLog
from src.graph import build_graph
from src.scenarios import clean_case, document, spouse_died_case
from tests.helpers import cfg, text_amount_extraction

SOURCE = Path(T.__file__)


def run_clean(tmp_path, thread="clean", **kwargs):
    graph = build_graph(trace_dir=tmp_path, **kwargs)
    return graph, graph.invoke(clean_case(), cfg(thread))


def spouse_run(tmp_path, thread="spouse"):
    case, agents = spouse_died_case()
    graph = build_graph(trace_dir=tmp_path, agents=agents)
    graph.invoke(case, cfg(thread))
    return graph


def row(snapshot, case_id):
    return next(r for r in T.runs(snapshot) if r["case_id"] == case_id)


# ---- a clean run -------------------------------------------------------------------------------


def test_a_clean_run_is_complete_with_the_expected_calls_in_order(tmp_path):
    run_clean(tmp_path)
    snap = T.Snapshot(tmp_path)
    assert row(snap, "clean")["outcome"] == T.COMPLETE
    calls = [t["agent"] for t in T.timeline(snap, "clean") if t["agent"] != "orchestrator"]
    assert calls == ["intake", "extraction", "rules", "computation", "review"]
    ends = [t for t in T.timeline(snap, "clean") if t["to"] == "end"]
    assert ends and all(t["reason"] for t in ends)


def test_token_totals_add_up_and_say_where_they_come_from(tmp_path):
    run_clean(tmp_path)
    snap = T.Snapshot(tmp_path)
    r = row(snap, "clean")
    per_agent = T.agents(snap)
    assert r["input_tokens"] == sum(a["input_estimated"] + a["input_reported"] for a in per_agent)
    assert r["output_tokens"] == sum(a["output_estimated"] + a["output_reported"] for a in per_agent)
    assert r["token_sources"]  # "estimate" for stubs, the provider for a real vision call


def test_agents_panel_has_every_agent_and_never_a_negative_time(tmp_path):
    run_clean(tmp_path)
    by_agent = {a["agent"]: a for a in T.agents(T.Snapshot(tmp_path))}
    assert {"orchestrator", "intake", "extraction", "rules", "computation", "review"} <= set(by_agent)
    assert all(a["calls"] >= 1 and a["avg_ms"] >= 0 and a["max_ms"] >= a["avg_ms"] for a in by_agent.values())


def test_a_clean_run_raises_no_alert_and_its_audit_chain_is_intact(tmp_path):
    run_clean(tmp_path)
    snap = T.Snapshot(tmp_path)
    assert T.safety(snap) == []
    chain = T.integrity(snap)
    assert [c["case_id"] for c in chain] == ["clean"] and chain[0]["intact"] and chain[0]["last_event"] == "draft_ready"


def test_overview_counts_cases_by_outcome(tmp_path):
    run_clean(tmp_path, "one")
    run_clean(tmp_path, "two")
    overview = T.overview(T.Snapshot(tmp_path))
    assert overview["cases"] == 2 and overview["by_outcome"] == {T.COMPLETE: 2}
    assert overview["needed_a_volunteer"] == 0 and overview["share_needing_a_volunteer"] == 0
    assert overview["alerts"] == 0 and overview["broken_chains"] == 0 and overview["unreadable_lines"] == 0


def test_an_empty_directory_gives_empty_panels_not_errors(tmp_path):
    snap = T.Snapshot(tmp_path / "nothing-here")
    assert T.runs(snap) == [] and T.agents(snap) == [] and T.escalations(snap) == []
    assert T.overview(snap)["cases"] == 0 and T.overview(snap)["share_needing_a_volunteer"] is None


# ---- a volunteer ---------------------------------------------------------------------------------


def test_a_waiting_case_is_awaiting_a_volunteer_and_the_pause_is_marked(tmp_path):
    spouse_run(tmp_path)
    snap = T.Snapshot(tmp_path)
    assert row(snap, "spouse")["outcome"] == T.WAITING
    assert any(t["paused_for_volunteer"] for t in T.timeline(snap, "spouse"))
    assert T.escalations(snap)[0]["condition"] == S.FILING_STATUS_AMBIGUITY
    assert T.escalations(snap)[0]["raised"] == 1 and T.escalations(snap)[0]["avg_wait_seconds"] is None


def test_a_resolved_escalation_shows_the_decision_and_the_wait(tmp_path):
    graph = spouse_run(tmp_path)
    graph.invoke(Command(resume={"decision": "continue", "note": "confirmed by phone", "reviewer": "Pat",
                                 "resolution": {"filing_status": "married_filing_jointly"}}), cfg("spouse"))
    snap = T.Snapshot(tmp_path)
    assert row(snap, "spouse")["outcome"] == T.COMPLETE
    esc = {e["condition"]: e for e in T.escalations(snap)}[S.FILING_STATUS_AMBIGUITY]
    assert (esc["raised"], esc["continued"], esc["stopped"]) == (1, 1, 0)
    assert esc["avg_wait_seconds"] is not None and esc["avg_wait_seconds"] >= 0
    assert T.overview(snap)["needed_a_volunteer"] == 1


def test_a_volunteer_stop_is_counted_as_stopped(tmp_path):
    graph = spouse_run(tmp_path)
    graph.invoke(Command(resume={"decision": "stop", "note": ""}), cfg("spouse"))
    snap = T.Snapshot(tmp_path)
    assert row(snap, "spouse")["outcome"] == T.STOPPED
    assert T.escalations(snap)[0]["stopped"] == 1


# ---- the orchestrator's own stops and the review loop --------------------------------------------


def test_a_loop_guard_stop_is_visible_as_an_escalation(tmp_path):
    graph = build_graph(trace_dir=tmp_path, agents={"computation": lambda view, tools: {}})
    graph.invoke(clean_case(), cfg("loop"))
    snap = T.Snapshot(tmp_path)
    assert {e["condition"]: e["raised"] for e in T.escalations(snap)}[S.LOOP_GUARD] == 1
    assert row(snap, "loop")["outcome"] == T.WAITING


def test_review_send_backs_are_counted(tmp_path):
    run_clean(tmp_path, "revision", agents={"extraction": text_amount_extraction})
    snap = T.Snapshot(tmp_path)
    assert row(snap, "revision")["review_rounds"] == 1 and row(snap, "revision")["outcome"] == T.COMPLETE
    assert T.review_loop(snap) == {"runs_with_send_back": 1, "rounds": {"revision": 1}, "bound_exceeded": 0}


def test_a_run_with_no_send_back_is_not_listed(tmp_path):
    run_clean(tmp_path)
    assert T.review_loop(T.Snapshot(tmp_path))["runs_with_send_back"] == 0


# ---- things that should never happen -------------------------------------------------------------


def test_a_write_outside_the_allow_list_is_an_alert(tmp_path):
    from src.orchestration.access import AccessViolation

    graph = build_graph(trace_dir=tmp_path, agents={"rules": lambda view, tools: {"computed": {}}})
    with pytest.raises(AccessViolation):
        graph.invoke(clean_case(), cfg("bad-write"))
    alerts = T.safety(T.Snapshot(tmp_path))
    assert [a["kind"] for a in alerts] == ["access_violation"] and alerts[0]["agent"] == "rules"
    assert "computed" in alerts[0]["detail"]


def test_a_tax_tool_run_in_the_agents_own_process_is_an_alert(tmp_path, monkeypatch):
    monkeypatch.setenv("SILVERFILE_TOOL_TRANSPORT", "local")
    run_clean(tmp_path)
    alerts = T.safety(T.Snapshot(tmp_path))
    assert alerts and {a["kind"] for a in alerts} == {"local_tax_tool"}
    assert {a["agent"] for a in alerts} <= {"computation", "review"}


def test_tax_tools_over_mcp_raise_no_alert(tmp_path):
    run_clean(tmp_path)
    records = [r for rs in T.Snapshot(tmp_path).runs.values() for r in rs if r["agent"] == "computation"]
    assert records and all(r["tool_transports"] == ["mcp"] for r in records)


def test_a_flagged_document_is_an_alert(tmp_path):
    AuditLog(tmp_path / "audit").record("doc-case", "document_flagged", "system:extraction", document="doc-1")
    alerts = T.safety(T.Snapshot(tmp_path))
    assert [a["kind"] for a in alerts] == ["document_flagged"]


def test_a_clean_halt_written_to_the_trace_is_an_alert_and_the_outcome(tmp_path):
    line = {"agent": "computation", "thread_id": "down", "step": 4, "ts": "2026-10-29T10:00:00+00:00",
            "duration_ms": 1.0, "handoff": {"from": "computation", "to": "end", "reason": "tool unreachable"},
            "error": "McpUnavailable", "violations": [], "tools_called": [], "tool_transports": []}
    (tmp_path / "down.jsonl").write_text(json.dumps(line) + "\n")
    snap = T.Snapshot(tmp_path)
    assert row(snap, "down")["outcome"] == T.HALTED
    assert [a["kind"] for a in T.safety(snap)] == ["halted_by_error"]


@pytest.mark.skipif(not hasattr(S, "HALTED_BY_ERROR"), reason="the clean halt arrives with #36")
def test_the_real_clean_halt_is_reported_as_halted(tmp_path, monkeypatch):
    from src.mcp_client import McpUnavailable
    from src.orchestration import access

    real_call = access.ToolBox.call

    def call(self, name, **kwargs):
        if name in T.TAX_TOOLS:
            raise McpUnavailable("down")
        return real_call(self, name, **kwargs)

    monkeypatch.setattr(access.ToolBox, "call", call)
    run_clean(tmp_path, "down")
    snap = T.Snapshot(tmp_path)
    assert row(snap, "down")["outcome"] == T.HALTED
    assert "halted_by_error" in {a["kind"] for a in T.safety(snap)}


# ---- damaged files -------------------------------------------------------------------------------


def test_a_tampered_audit_line_breaks_the_chain(tmp_path):
    graph = spouse_run(tmp_path)
    graph.invoke(Command(resume={"decision": "stop", "note": ""}), cfg("spouse"))
    path = tmp_path / "audit" / "spouse.jsonl"
    lines = path.read_text().splitlines()
    entry = json.loads(lines[1])
    entry["actor"] = "volunteer:someone-else"
    lines[1] = json.dumps(entry, sort_keys=True)
    path.write_text("\n".join(lines) + "\n")
    chain = {c["case_id"]: c for c in T.integrity(T.Snapshot(tmp_path))}["spouse"]
    assert not chain["intact"] and any("content was changed" in p for p in chain["problems"])
    assert T.overview(T.Snapshot(tmp_path))["broken_chains"] == 1


def test_a_corrupt_trace_line_is_skipped_and_counted(tmp_path):
    run_clean(tmp_path)
    with open(tmp_path / "clean.jsonl", "a") as fh:
        fh.write("{this is not json\n")
    snap = T.Snapshot(tmp_path)
    assert snap.unreadable_lines == 1
    assert row(snap, "clean")["outcome"] == T.COMPLETE
    assert T.overview(snap)["unreadable_lines"] == 1


def test_an_unreadable_audit_line_is_reported_not_raised(tmp_path):
    run_clean(tmp_path)
    with open(tmp_path / "audit" / "clean.jsonl", "a") as fh:
        fh.write("not json at all\n")
    snap = T.Snapshot(tmp_path)
    chain = T.integrity(snap)[0]
    assert not chain["intact"] and snap.unreadable_lines == 1


def test_a_case_with_an_audit_log_but_no_trace_is_still_listed(tmp_path):
    AuditLog(tmp_path / "audit").record("only-audit", "draft_ready", "agent:orchestrator")
    r = row(T.Snapshot(tmp_path), "only-audit")
    assert r["outcome"] == T.COMPLETE and r["calls"] == 0 and r["input_tokens"] is None


# ---- it only reads, and shows no values ----------------------------------------------------------


def test_the_module_cannot_write_and_never_reads_a_value_field():
    text = SOURCE.read_text()
    for forbidden in ("write_text", "open(", ".record(", "mkdir", "unlink", "rmtree", "Path.rename",
                      '"facts"', '"computed"', '"documents"', '"messages"', '"extracted"'):
        assert forbidden not in text, forbidden


def test_nothing_the_panels_return_holds_document_text_or_amounts(tmp_path):
    case = clean_case()
    case["documents"] = [document("doc-1")]
    graph = build_graph(trace_dir=tmp_path)
    graph.invoke(case, cfg("private"))
    snap = T.Snapshot(tmp_path)
    everything = json.dumps([T.runs(snap), T.timeline(snap, "private"), T.agents(snap), T.escalations(snap),
                             T.review_loop(snap), T.safety(snap), T.integrity(snap), T.overview(snap)])
    assert "TEST DATA" not in everything and "1000.00" not in everything
