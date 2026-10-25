from src.agents import computation, extraction, intake, review, rules

AGENTS = {
    "intake": intake.run,
    "extraction": extraction.run,
    "rules": rules.run,
    "computation": computation.run,
    "review": review.run,
}
