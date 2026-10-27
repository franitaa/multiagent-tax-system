"""A scripted taxpayer for driving the real Intake agent (feature/intake-agent) end to end.

Answers each question by matching its text, so it does not depend on the question order.
Defaults describe an in-scope single filer born in 1950 with one W-2. All data is made up.
"""
from langgraph.types import Command

from src.scenarios import clean_case, user

# (substring of the question, default answer); first match wins
DEFAULT_ANSWERS = (
    ("what is this person's full name", "Dana Dependent"),
    ("spouse's full name", "Sam Spouse"),
    ("full name", "Pat Taxpayer"),
    ("were you married", "no"),
    ("which of these fits you best", "single"),
    ("date of birth", "March 4, 1950"),
    ("legally blind", "no"),
    ("depend on you for support", "no"),
    ("w-2", "yes"),
    ("ssa-1099", "no"), ("1099-r", "no"), ("1099-int", "no"), ("1099-div", "no"),
    ("other tax forms", "no"), ("sell any stocks", "no"), ("own business", "no"),
    ("outside the united states", "no"), ("digital assets", "no"),
    ("tax payments to the irs", "no"), ("adjustments to your income", "no"),
    ("paid into a bank account or sent as a paper check", "paper check"),
    ("claim you as a dependent", "no"), ("spouse pass away", "no"),
    ("live in the united states", "yes"), ("answering these questions yourself", "yes"),
    ("is that right", "yes"), ("is that correct", "yes"),
)


class UnknownQuestion(Exception):  # not an AssertionError, so an xfail cannot hide it
    pass


def answer_for(question: str, overrides: dict | None = None) -> str:
    text = question.lower()
    table = list((overrides or {}).items()) + list(DEFAULT_ANSWERS)  # overrides win
    for key, answer in table:
        if key in text:
            return answer
    raise UnknownQuestion(f"the scripted taxpayer has no answer for: {question[:120]!r}")


def finish_interview(graph, config, result, overrides=None, max_questions=100):
    """Keep answering until the graph stops waiting for the taxpayer (done, or a human is needed).
    Returns (result, number of questions answered)."""
    asked = 0
    while "__interrupt__" not in result and result.get("status") == "awaiting_user":
        assert asked < max_questions, "interview did not finish"
        result = graph.invoke({"messages": [user(answer_for(result["pending_question"], overrides))]}, config)
        asked += 1
    return result, asked


def start_interview(graph, config, overrides=None):
    first = graph.invoke(clean_case(turns=1), config)
    return finish_interview(graph, config, first, overrides)


def resume(graph, config, decision, note, **extra):
    return graph.invoke(Command(resume={"decision": decision, "note": note, **extra}), config)
