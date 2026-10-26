"""Hub-and-spoke graph. Every agent node has exactly one outgoing edge, back to the
orchestrator; only the orchestrator has conditional edges."""
import os

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from src.agents import AGENTS
from src.orchestration.human import human_gate
from src.orchestration.orchestrator import orchestrate
from src.orchestration.runner import Runner
from src.state import END_KEY, HUMAN_KEY, SilverState


def _node(runner: Runner, name: str, fn):
    def node(state: SilverState, config: RunnableConfig):
        thread_id = config.get("configurable", {}).get("thread_id", "no-thread")
        return runner.run(name, fn, state, thread_id)

    node.__name__ = name
    return node


def _dispatcher(scoped: bool):
    """Conditional-edge function: the orchestrator's `next_agent`, except that extraction fans
    out into one parallel worker per pending document (LangGraph Send). Workers' results are
    merged by the order-independent `merge_extracted` reducer, then the orchestrator runs once.

    With the context strategy on, a worker's input is just its one document. With it off
    (the measurement baseline) it also receives the rest of the state."""

    def dispatch(state: SilverState):
        target = state["next_agent"]
        if target != "extraction":
            return target
        extracted = state.get("extracted", {})
        pending = [d for d in state.get("documents", []) if d["id"] not in extracted]
        return [
            Send("extraction", {"documents": [doc], "step": state.get("step", 0)} if scoped
                 else {**state, "documents": [doc]})
            for doc in pending
        ]

    return dispatch


def build_graph(checkpointer=None, *, trace_dir=None, context_strategy: bool = True, agents=None):
    """Compile the graph. A checkpointer is required for multi-turn intake and interrupts;
    InMemorySaver is the default (the memory owner will replace it).
    `agents` overrides stub/real agents by name (used by tests and scenarios)."""
    runner = Runner(
        trace_dir=trace_dir or os.environ.get("SILVERFILE_TRACE_DIR", "traces"),
        scoped=context_strategy,
    )
    builder = StateGraph(SilverState)
    builder.add_node("orchestrator", _node(runner, "orchestrator", orchestrate))
    agent_fns = {**AGENTS, **(agents or {})}
    builder.add_node(HUMAN_KEY, _node(runner, HUMAN_KEY, human_gate))
    builder.add_edge(HUMAN_KEY, "orchestrator")
    for name, fn in agent_fns.items():
        builder.add_node(name, _node(runner, name, fn))
        builder.add_edge(name, "orchestrator")
    builder.add_edge(START, "orchestrator")
    targets = {name: name for name in agent_fns} | {HUMAN_KEY: HUMAN_KEY, END_KEY: END}
    builder.add_conditional_edges("orchestrator", _dispatcher(context_strategy), targets)
    return builder.compile(checkpointer=checkpointer or InMemorySaver())
