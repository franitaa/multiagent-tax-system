"""The telemetry page draws what src/telemetry.py returns: no error, the right words, alerts first."""
import json
from pathlib import Path

import pytest
from langgraph.types import Command
from streamlit.testing.v1 import AppTest

from src.audit import AuditLog
from src.graph import build_graph
from src.scenarios import clean_case, spouse_died_case
from tests.helpers import cfg

PAGE = Path(__file__).resolve().parents[1] / "src" / "ui" / "telemetry_dashboard.py"


def open_page(folder, monkeypatch):
    monkeypatch.setenv("SILVERFILE_TRACE_DIR", str(folder))
    return AppTest.from_file(str(PAGE), default_timeout=30).run()


def text_of(page):
    parts = [h.value for h in page.header] + [h.value for h in page.title] + [s.value for s in page.subheader]
    parts += [m.value for m in page.markdown] + [e.value for e in page.error] + [s.value for s in page.success]
    parts += [str(m.value) for m in page.metric]
    return "\n".join(parts)


def make_runs(folder):
    build_graph(trace_dir=folder).invoke(clean_case(), cfg("clean-case"))
    case, agents = spouse_died_case()
    graph = build_graph(trace_dir=folder, agents=agents)
    graph.invoke(case, cfg("spouse-case"))
    graph.invoke(Command(resume={"decision": "continue", "note": "ok", "reviewer": "Pat",
                                 "resolution": {"filing_status": "married_filing_jointly"}}), cfg("spouse-case"))


def test_the_page_runs_on_an_empty_folder_and_says_so(tmp_path, monkeypatch):
    page = open_page(tmp_path / "nothing", monkeypatch)
    assert not page.exception
    assert page.success and "No alerts" in page.success[0].value
    assert [m.value for m in page.metric][0] == "0"


def test_the_page_lists_the_cases_with_plain_outcomes(tmp_path, monkeypatch):
    make_runs(tmp_path)
    page = open_page(tmp_path, monkeypatch)
    assert not page.exception
    cases = {r["Case"]: r for r in page.dataframe[1].value.to_dict("records")}
    assert set(cases) == {"clean-case", "spouse-case"}
    assert cases["clean-case"]["Outcome"] == "Draft ready"
    assert cases["spouse-case"]["Escalations"] == "FILING_STATUS_AMBIGUITY"
    assert [m.value for m in page.metric][:2] == ["2", "50%"]


def test_the_timeline_follows_the_picked_case(tmp_path, monkeypatch):
    make_runs(tmp_path)
    page = open_page(tmp_path, monkeypatch)
    assert "review" in set(page.dataframe[2].value["Agent"])
    page.selectbox[0].select("spouse-case").run()
    assert not page.exception
    assert "Paused for a volunteer" in page.dataframe[2].value.columns
    assert "yes" in set(page.dataframe[2].value["Paused for a volunteer"])


def test_an_alert_is_shown_first_and_in_words(tmp_path, monkeypatch):
    make_runs(tmp_path)
    AuditLog(tmp_path / "audit").record("clean-case", "document_flagged", "system:extraction", document="doc-1")
    page = open_page(tmp_path, monkeypatch)
    assert page.error and "ALERT" in page.error[0].value and not page.success
    flagged = page.dataframe[-2].value
    assert any("ALERT" in str(v) for v in flagged["What happened"])


def test_a_broken_audit_log_is_called_out_by_case(tmp_path, monkeypatch):
    make_runs(tmp_path)
    path = tmp_path / "audit" / "spouse-case.jsonl"
    lines = path.read_text().splitlines()
    entry = json.loads(lines[0])
    entry["actor"] = "someone-else"
    lines[0] = json.dumps(entry, sort_keys=True)
    path.write_text("\n".join(lines) + "\n")
    page = open_page(tmp_path, monkeypatch)
    assert "spouse-case" in page.error[0].value and "tamper check" in page.error[0].value
    assert any("ALERT" in str(v) for v in page.dataframe[-1].value["Tamper check"])


def test_a_damaged_line_is_reported_and_the_page_still_draws(tmp_path, monkeypatch):
    make_runs(tmp_path)
    with open(tmp_path / "clean-case.jsonl", "a") as fh:
        fh.write("{broken\n")
    page = open_page(tmp_path, monkeypatch)
    assert not page.exception and "could not be read" in page.error[0].value


def test_the_page_shows_no_document_text_or_amounts(tmp_path, monkeypatch):
    make_runs(tmp_path)
    page = open_page(tmp_path, monkeypatch)
    everything = text_of(page) + "".join(df.value.to_csv() for df in page.dataframe)
    assert "TEST DATA" not in everything and "1000.00" not in everything


def test_the_page_cannot_write():
    text = PAGE.read_text()
    for forbidden in ("write_text", "open(", ".record(", "mkdir", "unlink", "rmtree"):
        assert forbidden not in text, forbidden
