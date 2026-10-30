"""The audit log: who did what to a case. Tamper-evident, and free of personal data."""
import json

import pytest
from langgraph.types import Command

from src import state as S
from src.audit import AuditLog
from src.graph import build_graph
from src.scenarios import spouse_died_case
from tests.helpers import cfg


def test_entries_are_chained_and_verify(tmp_path):
    log = AuditLog(tmp_path)
    for event in ("a", "b", "c"):
        log.record("case-1", event, "agent:test", n=1)
    entries = log.read("case-1")
    assert [e["seq"] for e in entries] == [1, 2, 3]
    assert entries[1]["prev"] == entries[0]["hash"]
    assert log.verify("case-1") == []


def test_editing_or_deleting_an_entry_is_detected(tmp_path):
    log = AuditLog(tmp_path)
    for event in ("a", "b", "c"):
        log.record("case-1", event, "volunteer:Pat")
    path = log.path("case-1")
    lines = path.read_text().splitlines()

    edited = json.loads(lines[1])
    edited["actor"] = "volunteer:Someone Else"
    path.write_text("\n".join([lines[0], json.dumps(edited), lines[2]]) + "\n")
    assert any("content was changed" in p for p in log.verify("case-1"))

    path.write_text("\n".join([lines[0], lines[2]]) + "\n")  # middle entry removed
    assert log.verify("case-1")


def test_free_text_is_redacted_and_shortened(tmp_path):
    log = AuditLog(tmp_path)
    entry = log.record("case-1", "volunteer_decision", "volunteer:Pat",
                       note="Call 555-123-4567 or mail pat@example.com, SSN 123-45-6789 " + "x" * 500)
    note = entry["details"]["note"]
    assert "555-123-4567" not in note and "pat@example.com" not in note and "123-45-6789" not in note
    assert len(note) <= 300


def test_a_case_id_cannot_escape_the_audit_folder(tmp_path):
    log = AuditLog(tmp_path / "audit")
    log.record("../../evil", "x", "system:test")
    assert [p.parent for p in tmp_path.rglob("*.jsonl")] == [tmp_path / "audit"]


def spouse_run(tmp_path, reviewer):
    case, agents = spouse_died_case()
    graph = build_graph(trace_dir=tmp_path, agents=agents)
    graph.invoke(case, cfg("audit-case"))
    answer = {"decision": "continue", "note": "confirmed with the taxpayer",
              "resolution": {"filing_status": "married_filing_jointly"}}
    if reviewer:
        answer["reviewer"] = reviewer
    return graph.invoke(Command(resume=answer), cfg("audit-case")), AuditLog(tmp_path / "audit")


def test_a_volunteers_decision_is_recorded_with_who_made_it(tmp_path):
    result, log = spouse_run(tmp_path, "Pat Doe")
    assert result["status"] == S.COMPLETE
    events = [(e["event"], e["actor"]) for e in log.read("audit-case")]
    assert ("escalation_raised", "agent:intake") in events
    assert ("paused_for_volunteer", "system:human") in events
    assert ("volunteer_decision", "volunteer:Pat Doe") in events
    assert events[-1] == ("draft_ready", "agent:orchestrator")
    decision = next(e for e in log.read("audit-case") if e["event"] == "volunteer_decision")
    assert decision["details"]["condition"] == S.FILING_STATUS_AMBIGUITY
    assert decision["details"]["decision"] == "continue"
    assert decision["details"]["resolution_fields"] == ["filing_status"]
    assert log.verify("audit-case") == []


def test_a_decision_without_a_name_is_recorded_as_unidentified(tmp_path):
    _, log = spouse_run(tmp_path, None)
    assert "volunteer:unidentified" in [e["actor"] for e in log.read("audit-case")]


def test_the_audit_log_holds_no_amounts_or_answers(tmp_path):
    _, log = spouse_run(tmp_path, "Pat Doe")
    # Look at the entries without their hashes: a hash is 64 random hex characters and can contain
    # "1000" by chance (this test failed about once in a few hundred runs when it read the raw file).
    text = json.dumps([{k: v for k, v in e.items() if k not in ("hash", "prev", "ts")}
                       for e in log.read("audit-case")])
    assert "married_filing_jointly" not in text  # the resolution VALUE; only field names are kept
    assert "1000" not in text and "TEST DATA" not in text


def test_a_long_reviewer_name_is_shortened(tmp_path):
    _, log = spouse_run(tmp_path, "N" * 500)
    actor = next(e["actor"] for e in log.read("audit-case") if e["event"] == "volunteer_decision")
    assert len(actor) <= 80


def test_writing_a_draft_form_can_be_audited(tmp_path):
    from src.draft_form import write_draft_form
    from src.scenarios import clean_case

    result = build_graph(trace_dir=tmp_path / "t").invoke(clean_case(), cfg("form-case"))
    log = AuditLog(tmp_path / "audit")
    write_draft_form(result, tmp_path / "out", "form-case", audit=log, actor="volunteer:Pat Doe")
    entry = log.read("form-case")[-1]
    assert entry["event"] == "draft_form_written" and entry["actor"] == "volunteer:Pat Doe"
