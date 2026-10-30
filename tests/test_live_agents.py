"""One definition of the live agent set, shared by the chat page, the CLI and the dashboards.

AGENTS stays the offline default (a stub Intake that asks one canned question), because the
scenario tests and the long-session metrics need a short, deterministic interview. The real
Intake (24 questions) is wired through live_agents().
"""
from src.agents import AGENTS, intake, intake_agent, live_agents
from src.graph import build_graph
from src.scenarios import clean_case
from src.ui import chat_session
from tests.helpers import cfg


def test_live_agents_swaps_only_intake():
    live = live_agents()
    assert live["intake"] is intake_agent.run
    assert {k: v for k, v in live.items() if k != "intake"} == {k: v for k, v in AGENTS.items() if k != "intake"}


def test_the_offline_default_keeps_the_stub_intake():
    assert AGENTS["intake"] is intake.run


def test_the_chat_page_graph_uses_the_live_set(tmp_path):
    graph = chat_session.make_graph(trace_dir=tmp_path)
    result = graph.invoke(clean_case(turns=1), cfg("live-1"))
    assert result["status"] == "awaiting_user"
    assert "STUB" not in result["pending_question"]  # the real Intake asked, not the stub


def test_a_graph_built_from_the_live_set_asks_the_real_first_question(tmp_path):
    stub = build_graph(trace_dir=tmp_path / "a").invoke(clean_case(turns=1), cfg("stub"))
    live = build_graph(trace_dir=tmp_path / "b", agents=live_agents()).invoke(clean_case(turns=1), cfg("live"))
    assert "STUB" in stub["pending_question"]
    assert "STUB" not in live["pending_question"]
