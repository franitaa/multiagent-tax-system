"""Tests for the real Intake agent (src/agents/intake_agent.py). No network or model calls."""
import pytest
from langgraph.types import Command

from src import state as S
from src.agents import intake_agent as ia
from src.graph import build_graph
from src.scenarios import clean_case, user

NAME = "Pat Tester"  # answer to Q0 "What is your full name?"

# Answers after the name, for a single filer with one W-2 and nothing unusual.
ALL_NO_ANSWERS = [
    "no",              # Q1 married
    "single",          # Q3 situation
    "March 4, 1950",   # Q4 birth date
    "yes",             # Q4 confirm: "Just to check... Is that right?"
    "no",              # Q5 blind
    "no",              # Q8 dependents
    "yes",             # Q13 W-2
    "no", "no", "no", "no",  # Q14-Q17 other forms
    "no", "no", "no", "no", "no",  # Q17a-Q17e other forms, sales, business, abroad, digital assets
    "no",              # Q18 estimated payments
    "no",              # Q20 adjustments
    "paper check",     # Q20b refund
    "no",              # Q21 claimed as dependent
    "no",              # Q22 spouse died
    "yes",             # Q23 lived in US
    "yes",             # Q24 answering for self
]
Q21_AT, Q23_AT = 19, 21  # positions in ALL_NO_ANSWERS
FULL_ANSWERS = [NAME, *ALL_NO_ANSWERS]  # for tests that drive the whole graph


class Chat:
    """Plays the orchestrator's part: keeps messages and facts, calls Intake once per reply.
    Answers the name question first unless name=None."""

    def __init__(self, name=NAME):
        self.messages = [user("Hi, I need help with my 2025 return.")]
        self.facts = {}
        self.last = self._call()
        if name is not None:
            self.say(name)

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


@pytest.mark.parametrize("text", [
    "I don't know", "I do not know", "no idea", "unsure", "I can't remember", "I don’t remember",
    "I forgot", "no clue", "dunno", "idk", "Not certain",
])
def test_ways_of_saying_i_dont_know(text):
    assert ia.is_not_sure(text)


@pytest.mark.parametrize("text, expected", [
    ("March 4, 1950", "1950-03-04"), ("march 4 1950", "1950-03-04"), ("Mar 4th, 1950", "1950-03-04"),
    ("4 March 1950", "1950-03-04"), ("1950-03-04", "1950-03-04"),
    ("not sure", ia.NOT_SURE), ("sometime in 1950", None), ("March 4, 2030", None),
    ("I was born on March 4, 1950", "1950-03-04"), ("it's 4 March 1950 I think", "1950-03-04"),
    # forgiving about commas, dots and ordinals (every date is confirmed before saving)
    ("dec, 4,1950", "1950-12-04"), ("Dec. 4 1950", "1950-12-04"), ("december 4th,1950", "1950-12-04"),
    ("4th December 1950", "1950-12-04"), ("sept 9 1951", "1951-09-09"),
    # numbers only: never guess between month-first and day-first
    ("03/04/1950", ia.AMBIGUOUS_DATE), ("4/5/1950", ia.AMBIGUOUS_DATE),
    ("25/04/1950", "1950-04-25"), ("04/25/1950", "1950-04-25"), ("4/4/1950", "1950-04-04"),
    ("13/13/1950", None),
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
    choices = ia.question_for_key("Q3", {}).choices
    assert ia.parse_choice("I'm single", choices) == "single"
    assert ia.parse_choice("I am a widow", choices) == "widowed"
    assert ia.parse_choice("I take care of my grandson", choices) == "caring_for_someone"
    assert ia.parse_choice("dunno", choices) == ia.NOT_SURE
    assert ia.parse_choice("purple", choices) is None


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
    facts = {"taxpayer_name": {"value": NAME, "source": "user"},
             "married_dec31": {"value": "no", "source": "user"}}
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
    chat = Chat(name=None)
    assert chat.question.endswith("What is your full name?")
    assert chat.question.count("?") == 1
    assert chat.last["handoff_request"]["to"] == "end"
    assert set(chat.last["facts"]) == {ia.PROGRESS}  # only bookkeeping, no answers yet


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
    chat.say("yes")
    assert chat.question == "What is your spouse's full name?"
    for answer in ["Sam Tester", "June 1, 1952", "yes", "no"]:
        chat.say(answer)
    assert "spouse's date of birth" in chat.question
    chat.say("July 9, 1953")
    chat.say("yes")
    assert "spouse legally blind" in chat.question


def test_unclear_answer_is_asked_again_and_nothing_saved():
    chat = Chat()
    chat.say("purple")
    assert chat.question.startswith("Sorry, I didn't quite understand.")
    assert chat.question.endswith("were you married?")
    assert set(chat.facts) == {ia.PROGRESS, "taxpayer_name", ia.TRIES}  # no answer saved, only bookkeeping
    assert "married_dec31" not in chat.facts


def test_not_sure_is_saved_and_acknowledged():
    chat = Chat()
    chat.say("I'm not sure")
    assert chat.value("married_dec31") == ia.NOT_SURE
    assert chat.question.startswith(ia.NOT_SURE_ACK)


def test_two_dependents_with_practice_numbers():
    chat = Chat()
    for answer in ["no", "single", "March 4, 1950", "yes", "no", "yes"]:
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
    for answer in ["no", "single", "March 4, 1950", "yes", "no", "yes", "Ana Lopez", "granddaughter"]:
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


# ---- going back and changing answers (INT-3) --------------------------------------


@pytest.mark.parametrize("text, expected", [
    ("go back", True), ("Go back please", True), ("back", True), ("I want to change my answer", True),
    ("previous question", True), ("yes", False), ("I got money back", False),
])
def test_is_go_back(text, expected):
    assert ia.is_go_back(text) is expected


def test_go_back_reminds_earlier_answer_and_keeps_it():
    chat = Chat()
    chat.say("no")
    chat.say("single")
    chat.say("go back")
    assert chat.question == "Sure, let's go back. Earlier you said: single. " + ia.question_for_key("Q3", {}).text
    assert chat.value("household_situation") == "single"  # kept until a new answer is given
    chat.say("single")
    assert "date of birth" in chat.question  # same answer: carries on
    assert "history" not in chat.facts["household_situation"]


def test_go_back_at_first_question():
    chat = Chat(name=None)
    chat.say("go back")
    assert chat.question.startswith(ia.GO_BACK_FIRST)
    assert chat.question.endswith("What is your full name?")


def test_changed_answer_keeps_history_and_asks_new_questions():
    chat = Chat()
    chat.say("no")
    chat.say("single")
    chat.say("March 4, 1950")
    chat.say("yes")
    chat.say("go back")
    assert "Earlier you said: March 4, 1950." in chat.question
    chat.say("go back")
    chat.say("go back")
    assert "Earlier you said: no." in chat.question and chat.question.endswith("were you married?")
    chat.say("yes")
    # married now: the joint-return question applies and is asked next
    assert "file one tax return together" in chat.question
    assert chat.value("married_dec31") == "yes"
    assert chat.facts["married_dec31"]["history"] == [{"value": "no", "source": "user"}]
    chat.say("yes")
    chat.say("Sam Tester")  # spouse's name
    # birth date was already answered, so Intake carries on with the next open question
    assert "legally blind" in chat.question and "spouse" not in chat.question
    assert chat.value("taxpayer_birth_date") == "1950-03-04"


def test_go_back_to_change_a_dependent_name():
    chat = Chat()
    for answer in ["no", "single", "March 4, 1950", "yes", "no", "yes", "Ana Lopes"]:
        chat.say(answer)
    chat.say("go back")
    assert "Earlier you said: Ana Lopes." in chat.question
    chat.say("Ana Lopez")
    assert "How is Ana Lopez related" in chat.question
    person = chat.value("dependents")[0]
    assert person["name"] == "Ana Lopez"
    assert person["history"] == [{"name": "Ana Lopes"}]


def test_topic_of_only_matches_answered_questions():
    assert ia.topic_of("I was married", ["Q1"]) == "Q1"
    assert ia.topic_of("I was married", []) is None
    assert ia.topic_of("my wife was born in 1952", ["Q1", "Q4", "Q6"]) == "Q6"
    assert ia.topic_of("I was born in 1950", ["Q4"]) == "Q4"


def test_is_correction():
    assert ia.is_correction("Oh wait, I was married")
    assert ia.is_correction("I made a mistake")
    assert not ia.is_correction("yes")


def test_plain_correction_jumps_to_that_question():
    chat = Chat()
    for answer in ["no", "single", "March 4, 1950", "yes"]:
        chat.say(answer)
    assert "legally blind" in chat.question
    chat.say("Oh wait, actually I was married")
    assert chat.question == "No problem, let's fix that. Earlier you said: no. " + ia.question_for_key("Q1", {}).text
    chat.say("yes")
    assert "file one tax return together" in chat.question
    assert chat.facts["married_dec31"]["history"] == [{"value": "no", "source": "user"}]


def test_naming_an_earlier_question_jumps_to_it():
    chat = Chat()
    for answer in ["no", "single", "March 4, 1950", "yes"]:
        chat.say(answer)
    chat.say("I made a mistake")
    assert chat.question == ia.WHICH_ANSWER
    chat.say("my date of birth")
    assert "Earlier you said: March 4, 1950." in chat.question
    chat.say("March 4, 1951")
    chat.say("yes")
    assert chat.value("taxpayer_birth_date") == "1951-03-04"
    assert "legally blind" in chat.question


def test_not_understood_message_mentions_go_back():
    chat = Chat()
    chat.say("purple")
    assert ia.GO_BACK_TIP in chat.question


def test_correction_words_inside_a_free_text_answer_are_kept_as_the_answer():
    chat = Chat()
    for answer in ALL_NO_ANSWERS[:-1]:
        chat.say(answer)
    chat.say("no")  # someone else is answering
    chat.say("My daughter, actually. She has power of attorney and helps with my pension.")
    assert chat.last["intake_complete"] is True
    assert chat.value("helper_description").startswith("My daughter, actually.")


# ---- plain-words help ------------------------------------------------------------


@pytest.mark.parametrize("text, expected", [
    ("I didn't understand", True), ("what does that mean?", True), ("Huh?", True),
    ("what is a W-2?", True), ("I’m confused", True), ("yes", False),
    ("She understands my finances", False),
])
def test_is_confused(text, expected):
    assert ia.is_confused(text) is expected


def test_every_question_has_an_explanation():
    ids = {q.id for q in ia.BEFORE_DEPENDENTS + ia.AFTER_DEPENDENTS} | {"Q9", "Q10", "Q11", "Q12"}
    assert ids == set(ia.EXPLANATIONS)
    assert all("?" not in text for text in ia.EXPLANATIONS.values())  # no extra questions


def test_confused_person_gets_plain_explanation_and_same_question():
    chat = Chat()
    for answer in ["no", "single", "March 4, 1950", "yes"]:
        chat.say(answer)
    chat.say("I didn't understand")
    assert chat.question == f"No problem. {ia.EXPLANATIONS['Q5']} {ia.NOT_SURE_OK} Are you legally blind?"
    assert ia.GO_BACK_TIP not in chat.question
    chat.say("no")
    assert chat.value("taxpayer_blind") == "no"


def test_confused_on_a_dependent_question():
    chat = Chat()
    for answer in ["no", "single", "March 4, 1950", "yes", "no", "yes", "Ana Lopez"]:
        chat.say(answer)
    chat.say("what do you mean?")
    assert ia.EXPLANATIONS["Q10"] in chat.question
    assert "relationship" not in chat.value("dependents")[0]


# ---- not sure: flag for a volunteer (INT-5) ----------------------------------------


@pytest.mark.parametrize("text, expected", [
    ("Can I talk to a real person?", True), ("please flag this for a volunteer", True),
    ("I'd like to speak to someone", True), ("yes", False),
    ("My daughter is a volunteer at church", False), ("A person from my church helps me", False),
])
def test_wants_volunteer(text, expected):
    assert ia.wants_volunteer(text) is expected


def test_update_notes_adds_once_and_resolves():
    question = ia.question_for_key("Q5", {})  # Q5 blind
    facts = {}
    facts.update(ia.update_notes(question, ia.NOT_SURE, None, facts))
    assert ia.update_notes(question, ia.NOT_SURE, None, facts) == {}  # no duplicate note
    facts.update(ia.update_notes(question, "no", None, facts))
    assert facts[ia.NOTES]["value"] == [{"question": "Q5", "question_text": question.text,
                                         "reason": ia.REASON_NOT_SURE, "resolved": True}]
    assert ia.update_notes(question, "yes", None, facts) == {}


def test_not_sure_adds_a_volunteer_note_and_carries_on():
    chat = Chat()
    for answer in ["no", "single", "March 4, 1950", "yes"]:
        chat.say(answer)
    chat.say("I'm not sure")
    assert chat.question == f"{ia.NOT_SURE_ACK} {ia.question_for_key('Q8', {}).text}"
    assert chat.value(ia.NOTES) == [{"question": "Q5", "question_text": "Are you legally blind?",
                                     "reason": ia.REASON_NOT_SURE, "resolved": False}]
    assert chat.last["handoff_request"]["to"] == "end"  # no escalation: the chat goes on
    assert "escalation" not in chat.last


def test_asking_for_a_person_is_noted():
    chat = Chat()
    chat.say("Can I talk to a real person about this?")
    assert chat.question.startswith(ia.VOLUNTEER_ACK)
    assert chat.value("married_dec31") == ia.NOT_SURE
    assert chat.value(ia.NOTES)[0]["reason"] == ia.REASON_ASKED


def test_answering_later_resolves_the_note():
    chat = Chat()
    chat.say("not sure")
    chat.say("go back")
    assert "Earlier you said: not sure." in chat.question
    chat.say("no")
    assert chat.value("married_dec31") == "no"
    assert chat.value(ia.NOTES)[0]["resolved"] is True


def test_covered_topics_in_order_without_repeats():
    chat = Chat()
    for answer in ["no", "single", "March 4, 1950", "yes", "no", "yes", "Ana Lopez", "granddaughter"]:
        chat.say(answer)
    assert ia.covered_topics(chat.facts) == [
        "your name", "whether you were married", "your household", "your date of birth", "your eyesight",
        "people who depend on you",
    ]
    assert ia.welcome_back({}) == "Welcome back. We haven't covered any questions yet."


# ---- a Social Security number nobody asked for (INT-4) ----------------------------


def test_strip_volunteered_ssn():
    assert ia.strip_volunteered_ssn("no") == ("no", None)
    assert ia.strip_volunteered_ssn("no, it's 123-45-6789") == (f"no, it's {ia.SSN_REMOVED}", "real")
    assert ia.strip_volunteered_ssn("901 23 4567") == (ia.SSN_REMOVED, "practice")
    assert ia.strip_volunteered_ssn("901-23-4567 and 123456789")[1] == "real"
    assert ia.strip_volunteered_ssn("March 4, 1950")[1] is None
    assert ia.strip_volunteered_ssn("555-123-4567")[1] is None  # a phone number is not an SSN


def test_real_ssn_given_alone_is_not_saved_and_question_repeats():
    chat = Chat()
    update = chat.say("123-45-6789")
    assert update["pending_question"] == f"{ia.SSN_NOT_NEEDED_REAL} {ia.question_for_key('Q1', {}).text}"
    assert set(chat.facts) == {ia.PROGRESS, "taxpayer_name"}
    assert "123-45-6789" not in str(chat.facts)


def test_ssn_inside_an_answer_is_dropped_and_the_answer_kept():
    chat = Chat()
    update = chat.say("No, and my social security number is 123-45-6789")
    assert chat.value("married_dec31") == "no"
    assert update["pending_question"].startswith(ia.SSN_NOT_NEEDED_REAL)
    assert "123-45-6789" not in str(chat.facts) and "123-45-6789" not in update["pending_question"]


def test_practice_ssn_given_unasked_is_not_saved_either():
    chat = Chat()
    for answer in ["no", "single"]:
        chat.say(answer)
    update = chat.say("March 4, 1950. My number is 912-34-5678")
    assert update["pending_question"].startswith(ia.SSN_NOT_NEEDED + " Just to check:")
    chat.say("yes")
    assert chat.value("taxpayer_birth_date") == "1950-03-04"
    assert "912-34-5678" not in str(chat.facts)


# ---- dates are read back before saving; numbers alone are never guessed --------------


def test_date_is_confirmed_before_it_is_saved():
    chat = Chat()
    for answer in ["no", "single"]:
        chat.say(answer)
    chat.say("dec, 4,1950")
    assert chat.question == "Just to check: you were born on December 4, 1950. Is that right?"
    assert "taxpayer_birth_date" not in chat.facts  # nothing saved yet
    chat.say("yes")
    assert chat.value("taxpayer_birth_date") == "1950-12-04"
    assert "legally blind" in chat.question


def test_saying_no_to_the_check_asks_for_the_date_again():
    chat = Chat()
    for answer in ["no", "single", "March 4, 1950"]:
        chat.say(answer)
    chat.say("no")
    assert chat.question.startswith(ia.DATE_RETYPE) and "date of birth" in chat.question
    assert "taxpayer_birth_date" not in chat.facts
    chat.say("April 3, 1950")
    chat.say("yes")
    assert chat.value("taxpayer_birth_date") == "1950-04-03"


def test_a_new_date_during_the_check_is_checked_instead():
    chat = Chat()
    for answer in ["no", "single", "March 4, 1950"]:
        chat.say(answer)
    chat.say("no, it's March 5, 1950")
    assert "March 5, 1950. Is that right?" in chat.question
    chat.say("yes")
    assert chat.value("taxpayer_birth_date") == "1950-03-05"


def test_unclear_reply_to_the_check_repeats_the_check():
    chat = Chat()
    for answer in ["no", "single", "March 4, 1950"]:
        chat.say(answer)
    chat.say("purple")
    assert chat.question == f"{ia.CONFIRM_HINT} Just to check: you were born on March 4, 1950. Is that right?"


def test_numbers_that_could_be_two_dates_are_not_guessed():
    chat = Chat()
    for answer in ["no", "single"]:
        chat.say(answer)
    chat.say("03/04/1950")
    assert chat.question == ia.DATE_AMBIGUOUS
    assert "taxpayer_birth_date" not in chat.facts
    chat.say("April 3, 1950")
    assert "April 3, 1950. Is that right?" in chat.question


def test_spouse_date_is_checked_with_spouse_wording():
    chat = Chat()
    for answer in ["yes", "yes", "Sam Tester", "March 4, 1950", "yes", "no", "June 1, 1952"]:
        chat.say(answer)
    assert chat.question == "Just to check: your spouse was born on June 1, 1952. Is that right?"


# ---- "Your answers so far" and the Change buttons ----------------------------------


def test_answers_so_far_lists_answers_in_plain_words():
    chat = Chat()
    for answer in ["no", "single", "March 4, 1950", "yes", "not sure"]:
        chat.say(answer)
    rows = ia.answers_so_far(chat.facts)
    assert [(r["key"], r["answer"]) for r in rows] == [
        ("Q0", NAME), ("Q1", "no"), ("Q3", "single"), ("Q4", "March 4, 1950"), ("Q5", "not sure"),
    ]
    assert rows[3]["question"] == ia.question_for_key("Q4", {}).text


def test_answers_so_far_hides_questions_that_no_longer_apply():
    chat = Chat()
    for answer in ["yes", "yes", "Sam Tester", "March 4, 1950", "yes", "no", "June 1, 1952", "yes"]:
        chat.say(answer)
    assert "Q6" in [r["key"] for r in ia.answers_so_far(chat.facts)]
    chat.say(ia.CHANGE_PREFIX + ia.question_for_key("Q1", {}).text)
    chat.say("no")  # not married after all
    assert "Q6" not in [r["key"] for r in ia.answers_so_far(chat.facts)]
    assert chat.value("spouse_birth_date") == "1952-06-01"  # kept, never deleted


def test_answers_so_far_never_shows_ssn_digits():
    chat = Chat()
    for answer in ["no", "single", "March 4, 1950", "yes", "no", "yes", "Ana Lopez", "granddaughter",
                   "900-11-2222"]:
        chat.say(answer)
    rows = ia.answers_so_far(chat.facts)
    assert "900-11-2222" not in str(rows)
    assert {"key": "Q12:0", "question": rows[-1]["question"], "answer": "a practice number",
            "part": 3, "position": 4, "number": "3.4"} == rows[-1]


def test_change_button_jumps_back_and_then_carries_on():
    chat = Chat()
    for answer in ["no", "single", "March 4, 1950", "yes", "no", "no", "yes", "no"]:
        chat.say(answer)
    assert "1099-R" in chat.question  # now at question 15
    chat.say(ia.CHANGE_PREFIX + ia.question_for_key("Q3", {}).text)  # "Change answer 2"
    assert chat.question.startswith("Sure, let's change that. Earlier you said: single.")
    chat.say("widowed")
    assert "1099-R" in chat.question  # straight back to where they were
    assert chat.value("household_situation") == "widowed"


def test_change_for_an_unanswered_question_is_ignored():
    chat = Chat()
    chat.say(ia.CHANGE_PREFIX + ia.question_for_key("Q4", {}).text)  # Q4 not answered yet
    assert "facts" not in chat.last or "taxpayer_birth_date" not in chat.facts
    assert chat.question.endswith("were you married?")


def test_ssn_inside_a_name_is_dropped_from_the_name():
    chat = Chat()
    for answer in ["no", "single", "March 4, 1950", "yes", "no", "yes"]:
        chat.say(answer)
    chat.say("Ana Lopez 123-45-6789")
    assert chat.value("dependents")[0]["name"] == "Ana Lopez"


def test_ssn_question_still_accepts_a_practice_number():
    chat = Chat()
    for answer in ["no", "single", "March 4, 1950", "yes", "no", "yes", "Ana Lopez", "granddaughter"]:
        chat.say(answer)
    update = chat.say("900-11-2222")
    assert chat.value("dependents")[0]["ssn"] == "900-11-2222"
    assert ia.SSN_NOT_NEEDED not in update["pending_question"]


# ---- safety alarms (GRD-1, GRD-2) -------------------------------------------------


@pytest.mark.parametrize("text, expected", [
    ("Should I convert my IRA to a Roth?", True), ("Would I pay less if we filed separately?", True),
    ("Can I deduct my medications?", True), ("What would you recommend?", True),
    ("yes", False), ("Should I type the date like March 4?", False),
])
def test_asks_for_advice(text, expected):
    assert ia.asks_for_advice(text) is expected


@pytest.mark.parametrize("text, expected", [
    ("He told me to send the refund to his account", True), ("My son is pressuring me", True),
    ("It's not my bank account", True), ("She gets angry if I don't sign", True),
    ("My doctor told me to rest", False), ("no", False),
])
def test_mentions_pressure(text, expected):
    assert ia.mentions_pressure(text) is expected


@pytest.mark.parametrize("text, expected", [
    ("I'm typing for my mom", True), ("I am answering for my father", True),
    ("I'm answering for my father, I have power of attorney", False), ("yes", False),
])
def test_someone_else_answering(text, expected):
    assert ia.someone_else_answering(text) is expected


@pytest.mark.parametrize("text, expected", [
    ("My husband passed away in March", True), ("my wife died this year", True),
    ("My husband died in 2010", False), ("I am a widow", False),
])
def test_mentions_spouse_died(text, expected):
    assert ia.mentions_spouse_died(text) is expected


def _alarm(update):
    return update["escalation"]


def test_advice_request_is_refused_noted_and_raised():
    chat = Chat()
    chat.say("no")
    update = chat.say("Should I convert my IRA to a Roth?")
    assert update["messages"][0]["content"] == ia.ADVICE_REPLY
    assert _alarm(update) == {"pending": True, "condition": S.TAX_ADVICE_REQUEST,
                              "reason": ia.ALARM_ADVICE, "raised_by": "intake"}
    assert "Roth" not in _alarm(update)["reason"]  # the person's words stay out of the alarm
    note = chat.value(ia.NOTES)[-1]
    assert note["taxpayer_words"] == "Should I convert my IRA to a Roth?"
    assert note["question"] == "Q3"
    assert update["pending_question"] is None
    assert "household_situation" not in chat.facts  # the question is still open


def test_after_alarm_intake_asks_the_same_question_again():
    chat = Chat()
    chat.say("no")
    chat.say("Should I convert my IRA to a Roth?")
    chat.last = chat._call()  # the volunteer chose "continue": Intake runs with no new reply
    assert chat.question == ia.question_for_key("Q3", {}).text
    assert "escalation" not in chat.last


def test_pressure_raises_exploitation_calmly():
    chat = Chat()
    update = chat.say("He told me to send the refund to his account")
    assert update["messages"][0]["content"] == ia.CONCERN_REPLY
    assert _alarm(update)["condition"] == S.EXPLOITATION_SIGNS
    assert _alarm(update)["reason"] == ia.ALARM_PRESSURE


def test_third_party_without_permission_raises_exploitation():
    chat = Chat()
    update = chat.say("I'm typing for my mom, she is tired")
    assert _alarm(update)["condition"] == S.EXPLOITATION_SIGNS
    assert _alarm(update)["reason"] == ia.ALARM_THIRD_PARTY


def test_spouse_died_answer_raises_filing_status_ambiguity_and_keeps_answer():
    chat = Chat()
    for answer in ALL_NO_ANSWERS[:Q21_AT + 1]:  # up to Q21
        chat.say(answer)
    assert "pass away" in chat.question
    update = chat.say("yes")
    assert update["messages"][0]["content"] == ia.SPOUSE_DIED_REPLY
    assert _alarm(update)["condition"] == S.FILING_STATUS_AMBIGUITY
    assert chat.value("spouse_died_2025") == "yes"
    chat.last = chat._call()  # after "continue", Intake carries on with the next question
    assert "United States" in chat.question


def test_spouse_died_in_free_text():
    chat = Chat()
    update = chat.say("My husband passed away in March")
    assert _alarm(update)["condition"] == S.FILING_STATUS_AMBIGUITY


def test_helper_without_permission_raises_exploitation_and_ends_intake():
    chat = Chat()
    for answer in ALL_NO_ANSWERS[:-1]:
        chat.say(answer)
    chat.say("no")
    update = chat.say("My nephew Tom")
    assert chat.value("helper_description") == "My nephew Tom"
    assert _alarm(update)["condition"] == S.EXPLOITATION_SIGNS
    assert update["intake_complete"] is True


def test_q21_and_q23_are_only_recorded_for_rules_to_decide():
    chat = Chat()
    answers = list(ALL_NO_ANSWERS)
    answers[Q21_AT] = "not sure"
    answers[Q23_AT] = "no"
    for answer in answers:
        assert "escalation" not in chat.last
        chat.say(answer)
    assert chat.value("can_be_claimed_as_dependent") == ia.NOT_SURE
    assert chat.value("us_resident_all_year") == "no"
    assert chat.last["intake_complete"] is True


def _graph_until_question(tmp_path, thread_id, answers):
    graph = build_graph(trace_dir=tmp_path, agents={"intake": ia.run})
    config = {"configurable": {"thread_id": thread_id}}
    graph.invoke(clean_case(turns=1), config)
    for answer in [NAME, *answers]:
        graph.invoke({"messages": [user(answer)]}, config)
    return graph, config


def test_advice_alarm_pauses_graph_and_volunteer_continue_resumes(tmp_path):
    graph, config = _graph_until_question(tmp_path, "t-advice", ["no"])
    paused = graph.invoke({"messages": [user("Can I deduct my medications?")]}, config)
    assert paused["__interrupt__"][0].value["condition"] == S.TAX_ADVICE_REQUEST
    resumed = graph.invoke(Command(resume={"decision": "continue", "note": "Noted for the preparer"}), config)
    assert resumed["status"] == "awaiting_user"
    assert resumed["pending_question"] == ia.question_for_key("Q3", {}).text


def test_exploitation_alarm_pauses_graph_and_volunteer_can_stop(tmp_path):
    graph, config = _graph_until_question(tmp_path, "t-exploit", [])
    paused = graph.invoke({"messages": [user("My son is pressuring me to sign")]}, config)
    assert paused["__interrupt__"][0].value["condition"] == S.EXPLOITATION_SIGNS
    stopped = graph.invoke(Command(resume={"decision": "stop", "note": "Call the client"}), config)
    assert stopped["status"] == "halted_by_human"


def test_works_inside_the_real_graph(tmp_path):
    """Plugged into the orchestrator with stub agents for the rest: one graph call per reply."""
    graph = build_graph(trace_dir=tmp_path, agents={"intake": ia.run})
    config = {"configurable": {"thread_id": "t-intake"}}
    result = graph.invoke(clean_case(turns=1), config)
    assert result["status"] == "awaiting_user"
    for answer in FULL_ANSWERS:
        result = graph.invoke({"messages": [user(answer)]}, config)
    assert result["intake_complete"] is True
    assert result["status"] == "complete"
    assert result["facts"]["taxpayer_birth_date"]["value"] == "1950-03-04"


# ---- questions added after the assignment review ------------------------------------


def test_name_is_asked_first_and_saved():
    chat = Chat(name=None)
    chat.say("Pat Tester")
    assert chat.value("taxpayer_name") == "Pat Tester"
    assert chat.question.endswith("were you married?")


def test_spouse_name_only_for_a_joint_return():
    chat = Chat()
    chat.say("yes")  # married
    chat.say("yes")  # one return together
    assert chat.question == "What is your spouse's full name?"
    chat.say("Sam Tester")
    assert chat.value("spouse_name") == "Sam Tester"


def test_spouse_itemizing_only_when_filing_separately():
    chat = Chat()
    chat.say("yes")  # married
    chat.say("no")   # separate returns
    assert "list their deductions one by one" in chat.question
    chat.say("not sure")
    assert chat.value("spouse_itemizing") == ia.NOT_SURE


def test_year_of_death_only_for_widowed_with_dependents():
    chat = Chat()
    for answer in ["no", "widowed", "March 4, 1950", "yes", "no", "yes", "Ana Lopez", "granddaughter",
                   "900-11-2222", "no"]:
        chat.say(answer)
    assert chat.question == "In what year did your husband or wife pass away?"
    chat.say("She died in 2023")
    assert chat.value("spouse_death_year") == 2023


def test_no_year_of_death_question_without_dependents():
    chat = Chat()
    for answer in ["no", "widowed", "March 4, 1950", "yes", "no", "no"]:
        chat.say(answer)
    assert "W-2" in chat.question


@pytest.mark.parametrize("text, expected", [
    ("2023", 2023), ("in 2024", 2024), ("not sure", ia.NOT_SURE), ("2023 or 2024", None),
    ("1820", None), ("last year", None),
])
def test_parse_year(text, expected):
    assert ia.parse_year(text) == expected


def test_out_of_scope_screening_answers_are_only_recorded():
    chat = Chat()
    answers = list(ALL_NO_ANSWERS)
    answers[11:16] = ["yes", "yes", "yes", "yes", "yes"]  # Q17a-Q17e
    for answer in answers:
        assert "escalation" not in chat.last  # Intake does not judge scope; Rules does
        chat.say(answer)
    for name in ("has_other_tax_forms", "sold_stocks_or_property", "business_or_rental_income",
                 "foreign_income_or_accounts", "digital_assets"):
        assert chat.value(name) == "yes"
    assert chat.last["intake_complete"] is True


def _until_refund(chat):
    for answer in ALL_NO_ANSWERS[:18]:  # up to and including Q20 adjustments
        chat.say(answer)
    assert "refund" in chat.question


def test_refund_by_check_skips_the_bank_question():
    chat = Chat()
    _until_refund(chat)
    chat.say("a paper check please")
    assert chat.value("refund_method") == "paper_check"
    assert "claim you as a dependent" in chat.question


def test_refund_to_own_bank_account_carries_on():
    chat = Chat()
    _until_refund(chat)
    chat.say("into my bank account")
    assert "in your own name" in chat.question
    update = chat.say("yes")
    assert "escalation" not in update


@pytest.mark.parametrize("answer", ["no", "I'm not sure"])
def test_refund_to_someone_elses_account_raises_exploitation(answer):
    chat = Chat()
    _until_refund(chat)
    chat.say("bank account")
    update = chat.say(answer)
    assert update["escalation"]["condition"] == S.EXPLOITATION_SIGNS
    assert update["escalation"]["reason"] == ia.ALARM_REFUND_ACCOUNT
    assert update["messages"][0]["content"] == ia.CONCERN_REPLY


def test_unclear_refund_answer_gets_its_own_hint():
    chat = Chat()
    _until_refund(chat)
    chat.say("purple")
    assert "Please answer bank account or paper check." in chat.question


def test_spouse_can_be_claimed_only_when_married():
    chat = Chat()
    for answer in ["yes", "yes", "Sam Tester", "March 4, 1950", "yes", "no", "June 1, 1952", "yes", "no",
                   "no", "yes", "no", "no", "no", "no", "no", "no", "no", "no", "no", "no", "no",
                   "paper check", "no"]:
        chat.say(answer)
    assert chat.question == "Can another person claim your spouse as a dependent on their tax return?"


# ---- one shared SSN rule, and telling the person when a number was removed -----------


def test_intake_uses_the_security_owners_validator(monkeypatch):
    calls = []
    monkeypatch.setattr(ia, "is_fake_ssn", lambda digits: calls.append(digits) or True)
    assert ia.parse_ssn("123-45-6789") == ("123-45-6789", False)  # whatever security.py decides
    assert calls == ["123456789"]


def test_number_removed_by_the_chat_page_is_explained():
    chat = Chat()
    update = chat.say(f"no, my number is {ia.SSN_REMOVED}")
    assert update["pending_question"].startswith(ia.SSN_NOT_NEEDED_REAL)
    assert chat.value("married_dec31") == "no"


def test_number_removed_by_the_chat_page_at_the_ssn_question():
    chat = Chat()
    for answer in ["no", "single", "March 4, 1950", "yes", "no", "yes", "Ana Lopez", "granddaughter"]:
        chat.say(answer)
    update = chat.say(ia.SSN_REMOVED)
    assert update["pending_question"].startswith(ia.REAL_SSN)
    assert "ssn" not in chat.value("dependents")[0]



# ---- parts and "Skip for now" ------------------------------------------------------


def test_every_question_belongs_to_exactly_one_part():
    ids = [q.id for q in ia.BEFORE_DEPENDENTS + ia.AFTER_DEPENDENTS] + ["Q9", "Q10", "Q11", "Q12"]
    in_parts = [qid for _, part_ids in ia.PARTS for qid in part_ids]
    assert sorted(ids) == sorted(in_parts)
    assert ia.part_of("Q10:1") == 3


@pytest.mark.parametrize("text, expected", [
    ("skip", True), ("Skip for now", True), ("skip this question", True), ("later", True),
    ("I'll answer later", True), ("come back to this", True), ("no", False),
    ("My son skips meals", False), ("later this year", False),
])
def test_is_skip(text, expected):
    assert ia.is_skip(text) is expected


def test_skip_moves_on_and_saves_nothing():
    chat = Chat()
    update = chat.say("skip for now")
    assert update["pending_question"] == f"{ia.SKIP_ACK} {ia.question_for_key('Q4', {}).text}"
    assert "married_dec31" not in chat.facts
    assert chat.value(ia.SKIPPED) == ["Q1"]


def test_skipped_questions_come_back_at_the_end():
    chat = Chat()
    chat.say("skip")  # Q1 married: also hides Q2/Q3 until it is answered
    answers = [a for a in ALL_NO_ANSWERS if a not in ("single",)][1:]  # no Q1, no Q3
    for answer in answers:
        chat.say(answer)
    assert chat.question.endswith(
        "Thank you. There is 1 question we skipped. Let's look at it now. On December 31, 2025, were you married?")
    assert not chat.last.get("intake_complete")
    chat.say("no")
    assert "single, widowed" in chat.question  # Q3 now applies and is asked
    chat.say("single")
    assert chat.last["intake_complete"] is True
    assert chat.value(ia.SKIPPED) == []


def test_skipping_twice_counts_as_not_sure_for_a_volunteer():
    chat = Chat()
    for answer in ["no", "single", "March 4, 1950", "yes"]:
        chat.say(answer)
    chat.say("skip")  # Q5 blind
    chat.say("skip")  # Q8: nothing else left before Q8? no, Q8 is the next question
    for answer in ["yes", "no", "no", "no", "no", "no", "no", "no", "no", "no", "no", "no", "paper check",
                   "no", "no", "yes", "yes"]:
        chat.say(answer)
    assert "There are 2 questions we skipped" in chat.question
    chat.say("skip")  # Q5 again
    assert chat.value("taxpayer_blind") == ia.NOT_SURE
    assert chat.question.startswith(ia.NOT_SURE_ACK)
    assert chat.value(ia.NOTES)[-1]["question"] == "Q5"


def test_skipped_question_is_listed_and_can_be_answered_any_time():
    chat = Chat()
    chat.say("no")
    chat.say("skip")  # Q3
    rows = ia.answers_so_far(chat.facts)
    assert rows[-1] == {"key": "Q3", "question": ia.question_for_key("Q3", {}).text,
                        "answer": ia.SKIPPED_ANSWER, "part": 1, "position": 3, "number": "1.3"}
    chat.say(ia.CHANGE_PREFIX + rows[-1]["question"])
    assert chat.question.endswith(ia.question_for_key("Q3", {}).text)
    chat.say("widowed")
    assert chat.value("household_situation") == "widowed"
    assert chat.value(ia.SKIPPED) == []


def test_dependent_details_cannot_be_skipped_only_noted():
    chat = Chat()
    for answer in ["no", "single", "March 4, 1950", "yes", "no", "yes", "Ana Lopez"]:
        chat.say(answer)
    chat.say("skip")  # relationship: noted for a volunteer instead of left blank
    assert chat.value("dependents")[0]["relationship"] == ia.NOT_SURE


def test_overview_counts_skipped_and_volunteer_notes():
    chat = Chat()
    chat.say("no")
    chat.say("skip")       # Q3 skipped
    chat.say("March 4, 1950")
    chat.say("yes")
    chat.say("not sure")   # Q5 noted for a volunteer
    overview = {p["title"]: p["status"] for p in ia.parts_overview(chat.facts)}
    assert overview["Personal information"] == "In progress, 1 skipped"
    assert overview["Age and eyesight"] == "Done, 1 noted for a volunteer"
    assert overview["People who depend on you"] == "In progress"
    assert [p["current"] for p in ia.parts_overview(chat.facts)] == [False, False, True, False, False, False]


# ---- dates that do not exist ---------------------------------------------------------


@pytest.mark.parametrize("month, day, year, expected", [
    (4, 31, 1950, "April has only 30 days. Please check the day."),
    (2, 29, 1950, "February 1950 has only 28 days. Please check the day."),
    (2, 30, 1952, "February has only 29 days. Please check the day."),
    (2, 29, 1952, None), (4, 30, 1950, None), (12, 31, 1950, None),
])
def test_day_problem(month, day, year, expected):
    assert ia.day_problem(month, day, year) == expected


def test_typed_impossible_date_gets_a_clear_reason():
    chat = Chat()
    for answer in ["no", "single"]:
        chat.say(answer)
    chat.say("April 31, 1950")
    assert chat.question.startswith("That date doesn't exist: April has only 30 days. Please check the day.")
    assert "taxpayer_birth_date" not in chat.facts
