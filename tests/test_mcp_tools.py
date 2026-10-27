"""CMP-1: the tax tools are called over MCP, and give the same answers as the plain functions.

Assignment 7: Computation "must not do arithmetic itself: every number comes from a
deterministic MCP tool call". These tests start the real server (src/tax_math_mcp.py) over stdio."""
import json

import pytest

pytest.importorskip("mcp.server.mcpserver")

from src import mcp_client  # noqa: E402
from src.graph import build_graph  # noqa: E402
from src.mcp_client import McpToolClient, McpUnavailable, shared_client, tool_transport  # noqa: E402
from src.orchestration.access import ToolBox  # noqa: E402
from src.scenarios import clean_case, spouse_died_case  # noqa: E402
from src.tax_tools import TAX_TOOLS  # noqa: E402
from tests.helpers import cfg  # noqa: E402

CALLS = {  # one realistic call per tool
    "calculate_standard_deduction": dict(filing_status="married_filing_jointly", age_65_or_older=True,
                                         blind=False, spouse_age_65_or_older=True, spouse_blind=True),
    "calculate_senior_deduction": dict(magi=90000, qualifying_people=2, filing_status="married_filing_jointly"),
    "calculate_taxable_social_security": dict(benefits=18000, other_income=22000, tax_exempt_interest=150,
                                              filing_status="single"),
    "calculate_income_tax": dict(taxable_income=20000, filing_status="single"),
    "sum_amounts": dict(amounts={"a": 1.5, "b": 2.25}, label="line_x"),
    "subtract_amounts": dict(start=1000, subtract={"x": 250.5}, label="line_y", start_name="start"),
}


def test_the_call_table_covers_every_tool():
    assert set(CALLS) == set(TAX_TOOLS)


@pytest.mark.parametrize("name", sorted(CALLS))
def test_each_tool_over_mcp_gives_the_same_record_as_the_function(name):
    over_mcp = shared_client().call(name, **CALLS[name])
    direct = TAX_TOOLS[name](**CALLS[name])
    assert over_mcp == json.loads(json.dumps(direct))  # same value, formula, inputs, source, tool


def test_the_server_serves_the_tax_tools_and_nothing_else():
    import asyncio

    from src.tax_math_mcp import server

    assert {t.name for t in asyncio.run(server.list_tools())} == set(TAX_TOOLS)


def test_bad_input_is_a_value_error_like_the_plain_function():
    with pytest.raises(ValueError):
        shared_client().call("calculate_income_tax", taxable_income=1000, filing_status="martian")


def test_an_unknown_tool_is_refused():
    with pytest.raises(ValueError):
        shared_client().call("p3_extract_w2", document={})


def test_computation_tools_in_a_toolbox_go_over_mcp_and_say_so():
    box = ToolBox("computation")
    record = box.call("calculate_income_tax", taxable_income=20000, filing_status="single")
    assert record["value"] == TAX_TOOLS["calculate_income_tax"](20000, "single")["value"]
    assert box.transports == ["mcp"]


def test_the_transport_can_be_switched_to_local_on_purpose(monkeypatch):
    monkeypatch.setenv(mcp_client.TRANSPORT_ENV, "local")
    box = ToolBox("computation")
    box.call("calculate_income_tax", taxable_income=20000, filing_status="single")
    assert box.transports == ["local"]


def test_an_unknown_transport_setting_is_an_error(monkeypatch):
    monkeypatch.setenv(mcp_client.TRANSPORT_ENV, "carrier-pigeon")
    with pytest.raises(ValueError, match="mcp"):
        tool_transport()


def test_a_server_that_cannot_start_stops_the_run_with_a_clear_error(monkeypatch):
    monkeypatch.setattr(mcp_client, "STARTUP_TIMEOUT", 20)
    broken = McpToolClient(module="no_such_module_for_silverfile")
    with pytest.raises(McpUnavailable, match="tax tool server"):
        broken.call("calculate_income_tax", taxable_income=1, filing_status="single")


def test_no_silent_fallback_when_the_shared_client_is_broken(monkeypatch, tmp_path):
    """If MCP is selected and unreachable, Computation fails; it never computes in-process."""
    class Down:
        transport = "mcp"

        def tool(self, name):
            def call(**_):
                raise McpUnavailable("down")
            call.transport = "mcp"
            return call

    monkeypatch.setattr(mcp_client, "_shared", Down())
    with pytest.raises(McpUnavailable):
        build_graph(trace_dir=tmp_path).invoke(clean_case(), cfg("down"))


# ---- the whole graph over MCP ---------------------------------------------------------------


def amounts(result):
    return {line: record["value"] for line, record in result["computed"].items()}


def test_a_clean_run_computes_every_line_over_mcp_and_matches_the_local_functions(tmp_path, monkeypatch):
    over_mcp = build_graph(trace_dir=tmp_path / "mcp").invoke(clean_case(), cfg("mcp-run"))
    monkeypatch.setenv(mcp_client.TRANSPORT_ENV, "local")
    local = build_graph(trace_dir=tmp_path / "local").invoke(clean_case(), cfg("local-run"))

    assert over_mcp["status"] == "complete" and amounts(over_mcp) == amounts(local)

    def transports(directory, thread, agent):
        lines = (directory / f"{thread}.jsonl").read_text().splitlines()
        return [tuple(json.loads(x)["tool_transports"]) for x in lines if json.loads(x)["agent"] == agent]

    assert set(transports(tmp_path / "mcp", "mcp-run", "computation")) == {("mcp",)}
    assert set(transports(tmp_path / "mcp", "mcp-run", "review")) == {("mcp",)}
    assert set(transports(tmp_path / "local", "local-run", "computation")) == {("local",)}


def test_the_spouse_died_case_also_runs_over_mcp(tmp_path):
    from langgraph.types import Command

    case, agents = spouse_died_case()
    graph = build_graph(trace_dir=tmp_path, agents=agents)
    graph.invoke(case, cfg("mcp-spouse"))
    final = graph.invoke(Command(resume={"decision": "continue", "note": "confirmed",
                                         "resolution": {"filing_status": "married_filing_jointly"}}),
                         cfg("mcp-spouse"))
    assert final["status"] == "complete"
    assert final["computed"]["line_12e"]["inputs"]["filing_status"] == "married_filing_jointly"
    assert final["computed"]["line_12e"]["tool"] == "calculate_standard_deduction"
