"""Centralised access control: per-agent allow-lists for state fields and tools.

The runner enforces these. Reads are enforced structurally (an agent is handed a view
containing only its readable fields); writes are checked after the call; tools are only
reachable through the ToolBox the runner hands in.
"""
from dataclasses import dataclass
from typing import Callable

# Fields every agent may set so that safety signals and handoffs always work.
COMMON_WRITES = frozenset({"escalation", "handoff_request"})
# Fields every agent can always read, so a safety signal can never be scoped away.
ALWAYS_READ = ("escalation", "human_decisions")


@dataclass(frozen=True)
class AgentPolicy:
    reads: frozenset[str]
    writes: frozenset[str]
    tools: frozenset[str] = frozenset()


POLICY: dict[str, AgentPolicy] = {
    # The orchestrator "reads" the routing view (derived keys, see context.routing_view).
    "orchestrator": AgentPolicy(
        reads=frozenset(),  # filled from the routing view at run time
        writes=COMMON_WRITES
        | {
            "next_agent", "status", "done", "step", "handoff_log", "awaiting_since_msgs",
            "pending_question", "review", "review_history", "revision_count",
            "pending_revision", "human_decisions", "guard", "session_summary",
        },
    ),
    # The human gate is orchestrator-owned: it performs the interrupt and records the decision.
    "human": AgentPolicy(
        reads=frozenset({"case_id"}),
        writes=COMMON_WRITES | {"human_decisions", "status", "done", "facts"},
    ),
    "intake": AgentPolicy(
        reads=frozenset({"messages", "facts", "session_summary"}),
        writes=COMMON_WRITES | {"messages", "facts", "pending_question", "intake_complete"},
    ),
    "extraction": AgentPolicy(
        reads=frozenset({"documents"}),
        writes=COMMON_WRITES | {"extracted"},
    ),
    "rules": AgentPolicy(
        reads=frozenset({"facts", "extracted", "session_summary"}),
        writes=COMMON_WRITES | {"eligibility"},
    ),
    "computation": AgentPolicy(
        reads=frozenset({"facts", "extracted", "eligibility", "pending_revision"}),
        writes=COMMON_WRITES | {"computed"},
    ),
    "review": AgentPolicy(
        reads=frozenset({"computed", "eligibility", "session_summary"}),
        writes=COMMON_WRITES | {"review"},
    ),
}

# Tool registry. Teammates register their deterministic tools here by name, then list the
# name in the owning agent's `tools` above.
TOOLS: dict[str, Callable] = {}


class AccessViolation(Exception):
    """An agent wrote a field or called a tool outside its allow-list."""


class ToolBox:
    """The only way an agent can reach a tool. Refuses anything not on its allow-list."""

    def __init__(self, agent: str, registry: dict[str, Callable] | None = None):
        self.agent = agent
        self._allowed = POLICY[agent].tools
        self._registry = TOOLS if registry is None else registry
        self.calls: list[str] = []

    def call(self, name: str, **kwargs):
        if name not in self._allowed:
            raise AccessViolation(f"{self.agent} may not call tool {name!r}")
        self.calls.append(name)
        return self._registry[name](**kwargs)
