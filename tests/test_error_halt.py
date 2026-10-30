"""When the tax-tool server cannot be reached the run stops cleanly: status halted_by_error,
nothing computed, nothing filed, a trace and an audit entry, and no traceback to the caller.
(Before this the McpUnavailable exception escaped graph.invoke.)"""
import json

import pytest

from src import state as S
from src.audit import AuditLog
from src.graph import build_graph
from src.mcp_client import McpUnavailable
from src.orchestration import access
from src.scenarios import clean_case
from src.tax_tools import TAX_TOOLS
from src.ui import chat_session
from tests.helpers import cfg, read_trace


def run_with_server_down(tmp_path, monkeypatch, thread="down"):
    """Only the tax tools go over the server; Extraction's own tool keeps working."""
    real_call = access.ToolBox.call

    def call(self, name, **kwargs):
        if name in TAX_TOOLS:
            raise McpUnavailable("the tax tool server could not start: /secret/path/to/python missing")
        return real_call(self, name, **kwargs)

    monkeypatch.setattr(access.ToolBox, "call", call)
    graph = build_graph(trace_dir=tmp_path)
    return graph, graph.invoke(clean_case(), cfg(thread))


def test_an_unreachable_tool_server_halts_the_case_instead_of_raising(tmp_path, monkeypatch):
    graph, final = run_with_server_down(tmp_path, monkeypatch)
    assert final["status"] == S.HALTED_BY_ERROR and final["done"] is True
    assert not final.get("computed"), "no amount may be produced without the tool"
    assert final.get("review") in (None, {})


def test_the_halt_is_traced_by_error_type_only(tmp_path, monkeypatch):
    run_with_server_down(tmp_path, monkeypatch)
    records = read_trace(tmp_path, "down")
    halted = [r for r in records if r.get("error")]
    assert len(halted) == 1 and halted[0]["agent"] == "computation"
    assert halted[0]["error"] == "McpUnavailable"
    assert "/secret/path" not in json.dumps(records)  # the message may hold paths: it is not recorded


def test_the_halt_is_in_the_audit_log_and_the_chain_still_verifies(tmp_path, monkeypatch):
    run_with_server_down(tmp_path, monkeypatch)
    audit = AuditLog(tmp_path / "audit")
    events = [e["event"] for e in audit.read("down")]
    assert "halted_by_error" in events and "draft_ready" not in events
    assert audit.verify("down") == []  # no problems found
    assert "/secret/path" not in json.dumps(audit.read("down"))


def test_no_agent_runs_after_the_halt(tmp_path, monkeypatch):
    graph, final = run_with_server_down(tmp_path, monkeypatch)
    before = len(read_trace(tmp_path, "down"))
    graph.invoke({"messages": []}, cfg("down"))  # a later call on the same case
    after = [r["agent"] for r in read_trace(tmp_path, "down")][before:]
    assert "computation" not in after and "review" not in after


def test_the_chat_page_shows_the_neutral_stopped_screen(tmp_path, monkeypatch):
    graph, _ = run_with_server_down(tmp_path, monkeypatch, thread="page")
    assert chat_session.screen(graph, "page") == chat_session.STOPPED


def test_the_real_client_with_a_server_that_cannot_start_also_halts(tmp_path, monkeypatch):
    """No stub on ToolBox: the MCP client really tries to start a module that does not exist."""
    from src import mcp_client

    monkeypatch.setattr(mcp_client, "_shared", mcp_client.McpToolClient(module="src.no_such_module"))
    monkeypatch.setattr(mcp_client, "STARTUP_TIMEOUT", 20)
    final = build_graph(trace_dir=tmp_path).invoke(clean_case(), cfg("real"))
    assert final["status"] == S.HALTED_BY_ERROR and not final.get("computed")
