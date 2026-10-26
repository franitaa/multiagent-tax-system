"""Tests for the real Intake agent (src/agents/intake_agent.py). No network or model calls."""
import pytest

from src.agents import intake_agent as ia
from src.graph import build_graph
from src.scenarios import clean_case, user

ALL_NO_ANSWERS = [
    "no",              # Q1 married
    "single",          # Q3 situation
    "March 4, 1950",   # Q4 birth date
    "no",              # Q5 blind
    "no",              # Q8 dependents
    "yes",             # Q13 W-2
    "no", "no", "no", "no",  # Q14-Q17 other forms
    "no",              # Q18 estimated payments
    "no",              # Q20 adjustments
    "no",              # Q21 claimed as dependent
    "no",              # Q22 spouse died
    "yes",             # Q23 lived in US
    "yes",             # Q24 answering for self
]


class Chat:
    """Plays the orchestrator's part: keeps messages and facts, calls Intake once per reply."""

    def __init__(self):
        self.messages = [user("Hi, I need help with my 2025 return.")]
        self.facts = {}
        self.last = self._call()

    def _call(self):
        update = ia.run({"messages": list(self.messages), "facts": dict(self.facts)}, tools=None)
        self.messages += update.get("messages", [])
        self.facts.update(update.get("facts", {}))
        return update

    def say(self, text):
        self.messages.append(user(text))
        self.last = self._call()
        return self.last

    @property
    def question(self):
        return self.last.get("pending_question")

    def value(self, name):
        return self.facts[name]["value"]


# ---- answer parsing ---------------------------------------------------------------


@pytest.mark.parametrize("text, expected", [
    ("yes", "yes"), ("Yes.", "yes"), ("yep", "yes"), ("No", "no"), ("nope", "no"),
    ("I did not", "no"), ("I'm not sure", ia.NOT_SURE), ("I don’t know", ia.NOT_SURE),
    ("maybe", ia.NOT_SURE), ("yes and no", None), ("banana", None),
])
def test_parse_yes_no(text, expected):
    assert ia.parse_yes_no(text) == expected


@pytest.mark.parametrize("text, expected", [
    ("March 4, 1950", "1950-03-04"), ("march 4 1950", "1950-03-04"), ("Mar 4th, 1950", "1950-03-04"),
    ("4 March 1950", "1950-03-04"), ("1950-03-04", "1950-03-04"), ("03/04/1950", "1950-03-04"),
    ("not sure", ia.NOT_SURE), ("sometime in 1950", None), ("March 4, 2030", None),
])
def test_parse_date(text, expected):
    assert ia.parse_date(text) == expected


@pytest.mark.parametrize("text, expected", [
    ("1200", 1200.0), ("$1,200.50", 1200.5), ("about 800 dollars", 800.0),
    ("not sure", ia.NOT_SURE), ("200 or 300", None), ("a lot", None),
])
def test_parse_amount(text, expected):
    assert ia.parse_amount(text) == expected


def test_parse_choice():
    choices = ia.BEFORE_DEPENDENTS[2].choices
    assert ia.parse_choice("I'm single", choices) == "single"
    assert ia.parse_choice("I am a widow", choices) == "widowed"
    assert ia.parse_choice("I take care of my grandson", choices) == "caring_for_someone"
    assert ia.parse_choice("dunno", choices) is None


def test_parse_text():
    assert ia.parse_text("  Ana Lopez ") == "Ana Lopez"
    assert ia.parse_text("12345") is None
    assert ia.parse_text("I don't know") == ia.NOT_SURE


def test_parse_ssn_accepts_only_practice_numbers():
    assert ia.parse_ssn("900-12-3456") == ("900-12-3456", False)
    assert ia.parse_ssn("912 34 5678") == ("912-34-5678", False)
    assert ia.parse_ssn("123-45-6789") == (None, True)  # real-looking: refused
    assert ia.parse_ssn("12345") == (None, False)


# ---- choosing questions -----------------------------------------------------------


def test_next_question_skips_spouse_questions_when_not_married():
    facts = {"married_dec31": {"value": "no", "source": "user"}}
    assert ia.next_question(facts).id == "Q3"
    facts["household_situation"] = {"value": "single", "source": "user"}
    facts["taxpayer_birth_date"] = {"value": "1950-03-04", "source": "user"}
    facts["taxpayer_blind"] = {"value": "no", "source": "user"}
    assert ia.next_question(facts).id == "Q8"


def test_record_answer_keeps_amount_as_direct_user_input():
    question = next(q for q in ia.AFTER_DEPENDENTS if q.id == "Q19")
    saved = ia.record_answer(question, 1200.0, {})["estimated_payments_amount"]
    assert saved["value"] == 1200.0
    assert saved["source"] == "direct user input"
    assert {"entered_by", "entered_on"} <= set(saved)


# ---- whole conversations ----------------------------------------------------------


def test_first_message_welcomes_and_asks_one_question():
    chat = Chat()
    assert chat.question.endswith("On December 31, 2025, were you married?")
    assert chat.question.count("?") == 1
    assert chat.last["handoff_request"]["to"] == "end"
    assert "facts" not in chat.last


def test_full_conversation_single_filer():
    chat = Chat()
    for answer in ALL_NO_ANSWERS:
        assert not chat.last.get("intake_complete")
        chat.say(answer)
    assert chat.last["intake_complete"] is True
    assert chat.last["pending_question"] is None
    assert chat.last["handoff_request"]["to"] == "extraction"
    assert chat.value("taxpayer_birth_date") == "1950-03-04"
    assert chat.value("has_w2") == "yes"
    assert "spouse_birth_date" not in chat.facts and "file_jointly" not in chat.facts


def test_married_person_gets_spouse_questions():
    chat = Chat()
    chat.say("yes")
    assert "file one tax return together" in chat.question
    for answer in ["yes", "June 1, 1952", "no"]:
        chat.say(answer)
    assert "spouse's date of birth" in chat.question
    chat.say("July 9, 1953")
    assert "spouse legally blind" in chat.question


def test_unclear_answer_is_asked_again_and_nothing_saved():
    chat = Chat()
    chat.say("purple")
    assert chat.question.startswith("Sorry, I didn't quite understand.")
    assert chat.question.endswith("were you married?")
    assert chat.facts == {}


def test_not_sure_is_saved_and_acknowledged():
    chat = Chat()
    chat.say("I'm not sure")
    assert chat.value("married_dec31") == ia.NOT_SURE
    assert chat.question.startswith(ia.NOT_SURE_ACK)


def test_two_dependents_with_practice_numbers():
    chat = Chat()
    for answer in ["no", "single", "March 4, 1950", "no", "yes"]:
        chat.say(answer)
    chat.say("Ana Lopez")
    assert "How is Ana Lopez related" in chat.question
    chat.say("granddaughter")
    chat.say("900-11-2222")
    chat.say("yes")
    chat.say("Ben Lopez")
    chat.say("grandson")
    chat.say("901-33-4444")
    chat.say("no")
    assert chat.value("dependents") == [
        {"name": "Ana Lopez", "relationship": "granddaughter", "ssn": "900-11-2222"},
        {"name": "Ben Lopez", "relationship": "grandson", "ssn": "901-33-4444"},
    ]
    assert "W-2" in chat.question


def test_real_ssn_is_refused_never_saved_or_repeated():
    chat = Chat()
    for answer in ["no", "single", "March 4, 1950", "no", "yes", "Ana Lopez", "granddaughter"]:
        chat.say(answer)
    update = chat.say("123-45-6789")
    assert "facts" not in update
    assert "123-45-6789" not in update["messages"][0]["content"]
    assert update["pending_question"].startswith(ia.REAL_SSN)
    assert "ssn" not in chat.value("dependents")[0]


def test_helper_question_only_when_someone_else_answers():
    chat = Chat()
    for answer in ALL_NO_ANSWERS[:-1]:
        chat.say(answer)
    chat.say("no")
    assert "Who is helping you" in chat.question
    chat.say("My daughter Maria, she has power of attorney")
    assert chat.last["intake_complete"] is True
    assert chat.value("helper_description").startswith("My daughter Maria")


def test_works_inside_the_real_graph(tmp_path):
    """Plugged into the orchestrator with stub agents for the rest: one graph call per reply."""
    graph = build_graph(trace_dir=tmp_path, agents={"intake": ia.run})
    config = {"configurable": {"thread_id": "t-intake"}}
    result = graph.invoke(clean_case(turns=1), config)
    assert result["status"] == "awaiting_user"
    for answer in ALL_NO_ANSWERS:
        result = graph.invoke({"messages": [user(answer)]}, config)
    assert result["intake_complete"] is True
    assert result["status"] == "complete"
    assert result["facts"]["taxpayer_birth_date"]["value"] == "1950-03-04"
