"""Tests for the real Intake agent (src/agents/intake_agent.py). No network or model calls."""
import pytest
from langgraph.types import Command

from src import state as S
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
    assert set(chat.facts) == {ia.PROGRESS}


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
    assert chat.question == "Sure, let's go back. Earlier you said: single. " + ia.BEFORE_DEPENDENTS[2].text
    assert chat.value("household_situation") == "single"  # kept until a new answer is given
    chat.say("single")
    assert "date of birth" in chat.question  # same answer: carries on
    assert "history" not in chat.facts["household_situation"]


def test_go_back_at_first_question():
    chat = Chat()
    chat.say("go back")
    assert chat.question.startswith(ia.GO_BACK_FIRST)
    assert chat.question.endswith("were you married?")


def test_changed_answer_keeps_history_and_asks_new_questions():
    chat = Chat()
    chat.say("no")
    chat.say("single")
    chat.say("March 4, 1950")
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
    # birth date was already answered, so Intake carries on with the next open question
    assert "legally blind" in chat.question and "spouse" not in chat.question
    assert chat.value("taxpayer_birth_date") == "1950-03-04"


def test_go_back_to_change_a_dependent_name():
    chat = Chat()
    for answer in ["no", "single", "March 4, 1950", "no", "yes", "Ana Lopes"]:
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
    for answer in ["no", "single", "March 4, 1950"]:
        chat.say(answer)
    assert "legally blind" in chat.question
    chat.say("Oh wait, actually I was married")
    assert chat.question == "No problem, let's fix that. Earlier you said: no. " + ia.BEFORE_DEPENDENTS[0].text
    chat.say("yes")
    assert "file one tax return together" in chat.question
    assert chat.facts["married_dec31"]["history"] == [{"value": "no", "source": "user"}]


def test_naming_an_earlier_question_jumps_to_it():
    chat = Chat()
    for answer in ["no", "single", "March 4, 1950"]:
        chat.say(answer)
    chat.say("I made a mistake")
    assert chat.question == ia.WHICH_ANSWER
    chat.say("my date of birth")
    assert "Earlier you said: March 4, 1950." in chat.question
    chat.say("March 4, 1951")
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
    for answer in ["no", "single", "March 4, 1950"]:
        chat.say(answer)
    chat.say("I didn't understand")
    assert chat.question == f"No problem. {ia.EXPLANATIONS['Q5']} {ia.NOT_SURE_OK} Are you legally blind?"
    assert ia.GO_BACK_TIP not in chat.question
    chat.say("no")
    assert chat.value("taxpayer_blind") == "no"


def test_confused_on_a_dependent_question():
    chat = Chat()
    for answer in ["no", "single", "March 4, 1950", "no", "yes", "Ana Lopez"]:
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
    question = ia.BEFORE_DEPENDENTS[4]  # Q5 blind
    facts = {}
    facts.update(ia.update_notes(question, ia.NOT_SURE, None, facts))
    assert ia.update_notes(question, ia.NOT_SURE, None, facts) == {}  # no duplicate note
    facts.update(ia.update_notes(question, "no", None, facts))
    assert facts[ia.NOTES]["value"] == [{"question": "Q5", "question_text": question.text,
                                         "reason": ia.REASON_NOT_SURE, "resolved": True}]
    assert ia.update_notes(question, "yes", None, facts) == {}


def test_not_sure_adds_a_volunteer_note_and_carries_on():
    chat = Chat()
    for answer in ["no", "single", "March 4, 1950"]:
        chat.say(answer)
    chat.say("I'm not sure")
    assert chat.question == f"{ia.NOT_SURE_ACK} {ia.BEFORE_DEPENDENTS[7].text}"
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
    assert chat.question == ia.BEFORE_DEPENDENTS[2].text
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
    for answer in ALL_NO_ANSWERS[:13]:  # up to Q21
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
    answers[12] = "not sure"  # Q21
    answers[14] = "no"        # Q23
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
    for answer in answers:
        graph.invoke({"messages": [user(answer)]}, config)
    return graph, config


def test_advice_alarm_pauses_graph_and_volunteer_continue_resumes(tmp_path):
    graph, config = _graph_until_question(tmp_path, "t-advice", ["no"])
    paused = graph.invoke({"messages": [user("Can I deduct my medications?")]}, config)
    assert paused["__interrupt__"][0].value["condition"] == S.TAX_ADVICE_REQUEST
    resumed = graph.invoke(Command(resume={"decision": "continue", "note": "Noted for the preparer"}), config)
    assert resumed["status"] == "awaiting_user"
    assert resumed["pending_question"] == ia.BEFORE_DEPENDENTS[2].text


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
    for answer in ALL_NO_ANSWERS:
        result = graph.invoke({"messages": [user(answer)]}, config)
    assert result["intake_complete"] is True
    assert result["status"] == "complete"
    assert result["facts"]["taxpayer_birth_date"]["value"] == "1950-03-04"
