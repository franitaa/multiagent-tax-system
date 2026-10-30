from src.agents import computation, extraction, intake, review, rules

# The offline default. Intake is a stub that asks one canned question, so scenarios, tests and the
# context metrics stay short and deterministic. Entry points that talk to a person (the chat page,
# the CLI, the dashboards) use live_agents() instead.
AGENTS = {
    "intake": intake.run,
    "extraction": extraction.run,
    "rules": rules.run,
    "computation": computation.run,
    "review": review.run,
}


def live_agents() -> dict:
    """AGENTS with the real Intake (the 24-question interview) in place of the stub."""
    from src.agents import intake_agent  # imported on use: it is large and the stub set never needs it

    return {**AGENTS, "intake": intake_agent.run}
