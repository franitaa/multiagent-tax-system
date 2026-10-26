"""Intake agent (real version). Owner: Supriya Patil.

SUMMARY FOR THE TEAM
In one line: the only agent that talks to the taxpayer. It asks the questions in
docs/intake-script.md one at a time, saves the answers, and calls a volunteer when
something needs a human. It never does arithmetic and never explains tax rules.

What it can do today:
  - Ask and record (INT-2): one question at a time, skipping ones that do not apply.
    Understands yes / no / not sure, dates, names and amounts; asks again kindly if
    unclear. Answers are saved in `facts` under the shared names. Amounts are saved as
    "direct user input". Only practice SSNs starting with 9 are accepted; real-looking
    ones are refused and never saved or repeated.
  - Go back and change answers (INT-3): "go back", or a simple correction like "actually
    I was married", re-asks that question. Old answers are kept in `history`, never lost.
    "I don't understand" gets a plain-words explanation of the question.
  - "I'm not sure" (INT-5): always accepted, noted for a volunteer in `volunteer_notes`.
    The conversation carries on.
  - Safety alarms (GRD-1, GRD-2): a request for tax advice, a spouse who died in 2025,
    someone else answering without permission, or pressure about money or the refund
    account. Intake replies calmly, notes the person's words for the volunteer, and raises
    the escalation flag so the system pauses for a human. The flag itself holds no
    personal details.
  - Tested against tricky messages (GRD-3, tests/test_guardrails.py): disguised advice,
    indirect pressure, "ignore your instructions...", ALL CAPS, plus innocent sentences
    that must NOT raise an alarm. A real-looking SSN typed inside a sentence is replaced
    with "[number removed]" before anything is saved.

What is still missing:
  - Fuller handling of a volunteered SSN (INT-4) and the chat page (INT-6).
  - It uses keyword matching, not AI, so unusual wording can be missed. When in doubt it
    points the person to "go back" or a volunteer.

Notes for teammates:
  - Rules: Q21 (can someone claim you) and Q23 (lived in the US) are only recorded; Rules
    decides if they make the return out of scope. If an answer changes so a question no
    longer applies, the old answer is kept; use only answers whose question applies.
  - `intake_progress` in `facts` is Intake's own bookkeeping; other agents can ignore it.
  - Not plugged in yet: src/agents/intake.py is still the 2-message placeholder used by
    the orchestration tests.
"""
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from src.state import EXPLOITATION_SIGNS, FILING_STATUS_AMBIGUITY, TAX_ADVICE_REQUEST

NOT_SURE = "not_sure"

YES_NO = "yes_no"
CHOICE = "choice"
DATE = "date"
TEXT = "text"
AMOUNT = "amount"
SSN = "ssn"

WELCOME = (
    "Hello. I will ask you some questions about your 2025 taxes, one at a time. "
    "There are no wrong answers. You can say \"I'm not sure\" or \"go back\" at any time."
)
GO_BACK_FIRST = "We are at the first question, so there is nothing to go back to."
NOT_SURE_OK = "If you're not sure, that's fine, just say \"not sure\"."
GO_BACK_TIP ="If you want to change an earlier answer, just say \"go back\"."
WHICH_ANSWER = (
    "Which answer would you like to change? You can name it, for example \"my date of birth\", "
    "or say \"go back\"."
)
PROGRESS = "intake_progress"
NOT_SURE_ACK = "That's okay. I'll note this for a volunteer to help with."
VOLUNTEER_ACK = "Of course. I'll note that you'd like a volunteer to help with this question."
NOTES = "volunteer_notes"
REASON_NOT_SURE = "taxpayer not sure"
REASON_ASKED = "taxpayer asked for a person"

# Safety alarms (GRD-1, GRD-2). Replies are calm and never accuse anyone: a helper may be
# sitting next to the taxpayer. Alarm reasons are generic (they are written to traces);
# the person's own words go only into volunteer_notes.
ADVICE_REPLY = (
    "I'm here to help fill in your tax form, so I can't give tax advice. "
    "I'll note your question for the volunteer."
)
SPOUSE_DIED_REPLY = (
    "I'm very sorry for your loss. Thank you for telling me. "
    "A volunteer will look at this part with you before we go on."
)
CONCERN_REPLY = (
    "Thank you for telling me. Before we go on, I'm going to ask a volunteer to look at this with you."
)
ALARM_ADVICE = "taxpayer asked for tax advice"
ALARM_SPOUSE_DIED = "taxpayer says a spouse died in 2025"
ALARM_THIRD_PARTY = "someone else is answering without stated authority"
ALARM_PRESSURE = "taxpayer mentioned pressure or an unfamiliar refund account"
DONE = "Thank you. That was my last question. I'll now look at your documents."
REAL_SSN = (
    "That looks like a real Social Security number. To keep you safe, I did not save it. "
    "Please use a practice number that starts with 9, like 900-12-3456."
)
HINTS = {
    YES_NO: "Please answer yes, no, or not sure.",
    CHOICE: "Please answer single, widowed, or taking care of someone. You can also say not sure.",
    DATE: "Please type the date like this: March 4, 1950.",
    TEXT: "Please type a short answer.",
    AMOUNT: "Please type the amount as a number, like 1200.",
    SSN: "Please type a number that starts with 9, like 900-12-3456.",
}


# Plain-words help for each question, used when the person says they do not understand.
# They explain what the question means, never a tax rule or advice.
EXPLANATIONS = {
    "Q1": "This asks whether you had a husband or wife on December 31, 2025, the last day of the year. "
          "If you were separated or it feels complicated, you can say \"not sure\".",
    "Q2": "Married couples can send in one shared tax return for both of them, or one each. "
          "This asks if you plan to share one.",
    "Q3": "\"Widowed\" means your husband or wife has died. \"Taking care of someone\" means a child or "
          "relative lives with you and you support them. Otherwise, choose \"single\".",
    "Q4": "Please type the day you were born, with the month, day and year. For example: March 4, 1950.",
    "Q5": "\"Legally blind\" means a doctor has said your eyesight is very poor, even with glasses or "
          "contact lenses.",
    "Q6": "Please type the day your husband or wife was born, with the month, day and year. "
          "For example: June 1, 1952.",
    "Q7": "\"Legally blind\" means a doctor has said their eyesight is very poor, even with glasses or "
          "contact lenses.",
    "Q8": "This asks if someone, such as a child, grandchild or parent, relies on you for money to live.",
    "Q9": "Please type the first and last name of the person who relies on you.",
    "Q10": "For example: son, daughter, grandchild, or parent.",
    "Q11": "This asks if there is one more person who relies on you for money to live.",
    "Q12": "This is a practice system, so we never use real Social Security numbers. Please type any "
           "made-up number that starts with 9, like 900-12-3456.",
    "Q13": "A W-2 is a form an employer sends early in the year. It shows what you were paid at a job.",
    "Q14": "An SSA-1099 is a form the Social Security office mails you each January. It shows the "
           "Social Security money you received.",
    "Q15": "A 1099-R is a form you get if money was paid to you from a pension, an IRA, or another "
           "retirement account.",
    "Q16": "A 1099-INT is a form a bank sends you if your savings earned interest.",
    "Q17": "A 1099-DIV is a form you get if you own shares or funds that paid you dividends. "
           "Dividends are payments from companies.",
    "Q18": "Some people send money to the IRS during the year themselves, instead of waiting until "
           "they file. These are called estimated payments.",
    "Q19": "Please type the total you sent to the IRS during 2025, as a number. For example: 1200.",
    "Q20": "\"Adjustments\" are certain amounts that some people take off their income on a separate "
           "form called Schedule 1.",
    "Q20a": "Please type the total of those adjustments, as a number. If you have the form, it is on "
            "Schedule 1, line 26.",
    "Q21": "This asks if someone else, such as a son or daughter, lists you on their own tax return "
           "because they support you.",
    "Q22": "This asks if your husband or wife died at any time during 2025. We're sorry to ask about this.",
    "Q23": "This asks if you lived in the United States for the whole year, from January to December 2025.",
    "Q24": "This asks if you are the person typing these answers, or if someone else is typing them for you.",
    "Q25": "Please tell us the name of the person helping you and how you know them. A power of "
           "attorney is a legal paper that lets someone act for you.",
}


def _value(facts: dict, name: str):
    fact = facts.get(name)
    return fact.get("value") if isinstance(fact, dict) else None


def _always(facts: dict) -> bool:
    return True


def _when(name: str, value: str) -> Callable[[dict], bool]:
    return lambda facts: _value(facts, name) == value


@dataclass(frozen=True)
class Question:
    id: str
    fact: str
    kind: str
    text: str
    when: Callable[[dict], bool] = _always
    choices: dict = field(default_factory=dict)  # saved value -> words that mean it
    part: str | None = None  # for dependent questions: name / relationship / ssn / another
    index: int | None = None  # for dependent questions: which dependent (0 = first)

    @property
    def key(self) -> str:
        """Unique name for this question, e.g. "Q4", or "Q10:1" for the second dependent."""
        return self.id if self.index is None else f"{self.id}:{self.index}"


MARRIED = _when("married_dec31", "yes")

BEFORE_DEPENDENTS = [
    Question("Q1", "married_dec31", YES_NO, "On December 31, 2025, were you married?"),
    Question("Q2", "file_jointly", YES_NO,
             "Do you and your spouse plan to file one tax return together?", MARRIED),
    Question("Q3", "household_situation", CHOICE,
             "Which of these fits you best: single, widowed, or taking care of someone who lives with you?",
             _when("married_dec31", "no"),
             {"single": ("single",), "widowed": ("widow",), "caring_for_someone": ("care", "caring")}),
    Question("Q4", "taxpayer_birth_date", DATE, "What is your date of birth? For example: March 4, 1950."),
    Question("Q5", "taxpayer_blind", YES_NO, "Are you legally blind?"),
    Question("Q6", "spouse_birth_date", DATE, "What is your spouse's date of birth?", MARRIED),
    Question("Q7", "spouse_blind", YES_NO, "Is your spouse legally blind?", MARRIED),
    Question("Q8", "has_dependents", YES_NO,
             "Does anyone depend on you for support, such as a child or a relative?"),
]

AFTER_DEPENDENTS = [
    Question("Q13", "has_w2", YES_NO, "Did you get a W-2 form from a job this year?"),
    Question("Q14", "has_ssa_1099", YES_NO,
             "Did you get a Social Security benefits statement, called an SSA-1099?"),
    Question("Q15", "has_1099_r", YES_NO,
             "Did you get a form for money paid out of a pension or retirement account, called a 1099-R?"),
    Question("Q16", "has_1099_int", YES_NO, "Did you get a form showing bank interest, called a 1099-INT?"),
    Question("Q17", "has_1099_div", YES_NO, "Did you get a form showing dividends, called a 1099-DIV?"),
    Question("Q18", "made_estimated_payments", YES_NO,
             "During 2025, did you send any tax payments to the IRS yourself?"),
    Question("Q19", "estimated_payments_amount", AMOUNT, "About how much did you send in total?",
             _when("made_estimated_payments", "yes")),
    Question("Q20", "has_adjustments", YES_NO,
             "Do you have any adjustments to your income that you want to include?"),
    Question("Q20a", "adjustments_amount", AMOUNT, "What is the total amount of those adjustments?",
             _when("has_adjustments", "yes")),
    Question("Q21", "can_be_claimed_as_dependent", YES_NO,
             "Can another person claim you as a dependent on their tax return?"),
    Question("Q22", "spouse_died_2025", YES_NO, "Did a spouse pass away during 2025?"),
    Question("Q23", "us_resident_all_year", YES_NO, "Did you live in the United States for all of 2025?"),
    Question("Q24", "answering_for_self", YES_NO, "Are you answering these questions yourself today?"),
    Question("Q25", "helper_description", TEXT,
             "Who is helping you, and are they allowed to act for you, for example with a power of attorney?",
             _when("answering_for_self", "no")),
]


# ---- choosing the next question ---------------------------------------------------


def _dependent(question_id: str, index: int, facts: dict) -> Question:
    """Q9-Q12 for the dependent at `index` (0 = first)."""
    dependents = _value(facts, "dependents") or []
    current = dependents[index] if index < len(dependents) else {}
    name = current.get("name", NOT_SURE)
    name = name if name != NOT_SURE else "this person"
    if question_id == "Q9":
        return Question("Q9", "dependents", TEXT, "What is this person's full name?", part="name", index=index)
    if question_id == "Q10":
        return Question("Q10", "dependents", TEXT, f"How is {name} related to you?",
                        part="relationship", index=index)
    if question_id == "Q12":
        return Question(
            "Q12", "dependents", SSN,
            f"For this test, please use a practice Social Security number that starts with 9. "
            f"What is the practice number for {name}?",
            part="ssn", index=index,
        )
    return Question("Q11", "dependents", YES_NO, "Does anyone else depend on you for support?",
                    part="another", index=index)


def _dependent_question(facts: dict) -> Question | None:
    """Q9-Q12 repeat for each dependent; Q11 asks whether there is another one."""
    if _value(facts, "has_dependents") != "yes" or _value(facts, "dependents_complete") == "yes":
        return None
    dependents = _value(facts, "dependents") or []
    index = max(len(dependents) - 1, 0)
    current = dependents[index] if dependents else {}
    for question_id, part in (("Q9", "name"), ("Q10", "relationship"), ("Q12", "ssn")):
        if part not in current:
            return _dependent(question_id, index, facts)
    return _dependent("Q11", index, facts)


def question_for_key(key: str, facts: dict) -> Question | None:
    """Turn a question key back into the question (used when going back)."""
    if ":" in key:
        question_id, index = key.split(":")
        return _dependent(question_id, int(index), facts)
    return next((q for q in BEFORE_DEPENDENTS + AFTER_DEPENDENTS if q.id == key), None)


def next_question(facts: dict) -> Question | None:
    """The first question that applies and has no answer yet. None when intake is finished."""
    for question in BEFORE_DEPENDENTS:
        if question.when(facts) and question.fact not in facts:
            return question
    dependent = _dependent_question(facts)
    if dependent:
        return dependent
    for question in AFTER_DEPENDENTS:
        if question.when(facts) and question.fact not in facts:
            return question
    return None


# ---- understanding answers --------------------------------------------------------

_NOT_SURE_PHRASES = ("not sure", "unsure", "don't know", "dont know", "do not know", "no idea",
                     "not certain", "maybe")
_YES_WORDS = {"yes", "y", "yeah", "yep", "yup", "correct", "sure", "true"}
_NO_WORDS = {"no", "n", "nope", "nah", "never", "false", "not"}
_DATE_FORMATS = ("%B %d, %Y", "%B %d %Y", "%b %d, %Y", "%b %d %Y", "%d %B %Y", "%d %b %Y",
                 "%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y")
_SSN_PATTERN = re.compile(r"^(\d{3})[- ]?(\d{2})[- ]?(\d{4})$")
_SSN_INSIDE_TEXT = re.compile(r"\b(\d{3})[- ]?(\d{2})[- ]?(\d{4})\b")
SSN_REMOVED = "[number removed]"


def redact_ssn(text: str) -> str:
    """Replace any real-looking SSN inside a sentence; practice numbers (9XX) are left alone."""
    return _SSN_INSIDE_TEXT.sub(lambda m: m.group(0) if m.group(1).startswith("9") else SSN_REMOVED, text)


_GO_BACK_EXACT = {"back", "go back", "previous", "previous question", "undo"}
_GO_BACK_PHRASES = ("go back", "change my answer", "change my last answer", "previous question")


def is_go_back(text: str) -> bool:
    lowered = re.sub(r"[^a-z ]", "", text.lower()).strip()
    return lowered in _GO_BACK_EXACT or any(phrase in lowered for phrase in _GO_BACK_PHRASES)


_CORRECTION_WORDS = re.compile(r"\b(actually|wait|i meant|i mean|mistake|wrong|oops|change|fix)\b")

# Words that point to an earlier question, checked in this order (spouse questions before
# the person's own, so "my wife was born..." means Q6, not Q4).
_TOPICS = (
    ("Q6", (("spouse", "wife", "husband"), ("born", "birth"))),
    ("Q7", (("spouse", "wife", "husband"), ("blind",))),
    ("Q21", (("claim",),)),
    ("Q22", (("passed away", "died", "death"),)),
    ("Q2", (("together", "jointly", "joint"),)),
    ("Q1", (("married", "marriage"),)),
    ("Q3", (("single", "widow", "take care", "taking care", "caring"),)),
    ("Q4", (("born", "birth"),)),
    ("Q5", (("blind",),)),
    ("Q8", (("dependent", "depend"),)),
    ("Q13", (("w-2", "w2"),)),
    ("Q14", (("ssa", "social security"),)),
    ("Q15", (("1099-r", "pension", "retirement"),)),
    ("Q16", (("interest", "1099-int"),)),
    ("Q17", (("dividend", "1099-div"),)),
    ("Q18", (("estimated", "payment"),)),
    ("Q20", (("adjustment",),)),
    ("Q23", (("lived", "live in", "united states", "abroad"),)),
)


_CONFUSED_PHRASES = ("don't understand", "dont understand", "didn't understand", "didnt understand",
                     "do not understand", "did not understand", "what does that mean",
                     "what does this mean", "what do you mean", "what is a", "what's a", "what is that",
                     "what's that", "confused", "explain", "huh", "don't get it", "dont get it", "pardon")


def is_confused(text: str) -> bool:
    lowered = text.lower().replace("’", "'")
    return any(phrase in lowered for phrase in _CONFUSED_PHRASES)


_VOLUNTEER_PHRASES = ("a volunteer", "real person", "talk to a person", "speak to a person",
                      "speak with a person", "a human", "talk to someone", "speak to someone",
                      "speak with someone", "flag this", "flag it")
_VOLUNTEER_NOT = ("volunteer at", "volunteers at", "is a volunteer", "was a volunteer")


def wants_volunteer(text: str) -> bool:
    """"Can I talk to a real person?" / "flag this for a volunteer"."""
    lowered = text.lower()
    if any(phrase in lowered for phrase in _VOLUNTEER_NOT):
        return False
    return any(phrase in lowered for phrase in _VOLUNTEER_PHRASES)


# ---- safety listeners (GRD-1) -----------------------------------------------------

_ADVICE_PHRASES = ("can i deduct", "can we deduct", "can i claim", "would i pay less", "would we pay less",
                   "pay less tax", "save on tax", "save on my tax", "lower my tax", "reduce my tax",
                   "better for me", "better for us", "is it better to", "would it be better", "is it smarter",
                   "bigger refund", "larger refund", "what do you recommend", "what would you recommend",
                   "your advice", "tax advice")
# "should I file...", "whether she should file...", "tell me if I should file..."
_ADVICE_SHOULD = re.compile(
    r"\b(?:should (?:i|we|she|he|they)|(?:i|we|she|he|they) should)\b.*?\b(?:convert|file|deduct|claim|"
    r"take|withdraw|sell|pay|itemi[sz]e|ira|separately|jointly|invest|move)"
)
# Always a warning sign.
_PRESSURE_STRONG = ("pressur", "threaten", "forcing me", "forced me", "or else", "scared of", "not my account",
                    "not my bank", "whose account", "don't know the account", "don't know which account",
                    "don't know the bank", "takes my money", "took my money", "takes my refund",
                    "took my refund", "keeps my bank card", "keeps my card", "has my bank card", "took my card")
# A warning sign only when money or answers are mentioned too ("my doctor told me to rest" is fine).
_PRESSURE_WEAK = ("told me to", "telling me to", "making me", "made me", "gets angry", "get angry",
                  "says i have to", "says i must", "have to give", "must give",
                  "his account", "her account", "their account")
# Whole words only, so "accountant" does not count as "account".
_MONEY_WORDS = re.compile(r"\b(?:refund|money|account|bank|sign|say|answer|check)\b")
_RELATIVES = (r"(?:(?:my|our) )?(?:mother|mom|mum|father|dad|grandmother|grandma|grandfather|grandpa|"
              r"aunt|uncle|husband|wife|parents?|sister|brother|friend|neighbou?r)")
# "I'm answering for mom", "doing it for her", "filling this out for my grandmother", "on behalf of"
_THIRD_PARTY = re.compile(
    r"\bon behalf of\b|\b(?:answering|typing|doing|filling)\b(?: (?:this|it))?(?: (?:out|in))? for "
    rf"(?:her|him|them|{_RELATIVES})\b"
)
_AUTHORITY = ("power of attorney", "poa", "guardian", "conservator", "authori", "permission",
              "allowed", "legal")
_SPOUSE_WORDS = ("husband", "wife", "spouse", "partner")
_DEATH_WORDS = ("died", "passed away", "passed on", "passed in", "passed last", "passed this",
                "passed recently", "death", "lost my")


def _lower(text: str) -> str:
    return text.lower().replace("’", "'")


def asks_for_advice(text: str) -> bool:
    lowered = _lower(text)
    return any(p in lowered for p in _ADVICE_PHRASES) or bool(_ADVICE_SHOULD.search(lowered))


def mentions_pressure(text: str) -> bool:
    lowered = _lower(text)
    if any(p in lowered for p in _PRESSURE_STRONG):
        return True
    return any(p in lowered for p in _PRESSURE_WEAK) and bool(_MONEY_WORDS.search(lowered))


def has_authority(text: str) -> bool:
    return any(word in _lower(text) for word in _AUTHORITY)


def someone_else_answering(text: str) -> bool:
    """A third party says they are answering, and no permission (e.g. power of attorney) is stated."""
    return bool(_THIRD_PARTY.search(_lower(text))) and not has_authority(text)


def mentions_spouse_died(text: str) -> bool:
    """e.g. "my husband passed away in March". Not when an earlier year is named ("died in 2010")."""
    lowered = _lower(text)
    years = re.findall(r"\b(?:19|20)\d\d\b", lowered)
    if any(year != "2025" for year in years):
        return False
    return any(w in lowered for w in _SPOUSE_WORDS) and any(w in lowered for w in _DEATH_WORDS)


def is_correction(text: str) -> bool:
    return bool(_CORRECTION_WORDS.search(text.lower()))


def topic_of(text: str, answered: list[str]) -> str | None:
    """The already-answered question this message talks about, e.g. "I was married" -> "Q1"."""
    lowered = text.lower()
    for question_id, groups in _TOPICS:
        if question_id in answered and all(any(w in lowered for w in group) for group in groups):
            return question_id
    return None


def is_not_sure(text: str) -> bool:
    lowered = text.lower().replace("’", "'")
    return any(phrase in lowered for phrase in _NOT_SURE_PHRASES)


def parse_yes_no(text: str) -> str | None:
    if is_not_sure(text):
        return NOT_SURE
    words = set(re.findall(r"[a-z]+", text.lower()))
    yes, no = bool(words & _YES_WORDS), bool(words & _NO_WORDS)
    if yes and not no:
        return "yes"
    if no and not yes:
        return "no"
    return None


def parse_choice(text: str, choices: dict) -> str | None:
    if is_not_sure(text):
        return NOT_SURE
    lowered = text.lower()
    matches = [value for value, words in choices.items() if any(w in lowered for w in words)]
    return matches[0] if len(matches) == 1 else None


def parse_date(text: str) -> str | None:
    """A birth date as YYYY-MM-DD, or None if it cannot be read or is not a sensible birth date."""
    if is_not_sure(text):
        return NOT_SURE
    cleaned = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", text.strip().rstrip("."))
    cleaned = re.sub(r"\s+", " ", cleaned)
    for fmt in _DATE_FORMATS:
        try:
            parsed = datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
        return parsed.isoformat() if 1900 <= parsed.year <= 2025 else None
    return None


def parse_amount(text: str) -> float | None:
    """The single number the person typed (e.g. "$1,200" -> 1200.0). Not a calculation."""
    if is_not_sure(text):
        return NOT_SURE
    numbers = re.findall(r"\d+(?:\.\d+)?", text.replace(",", ""))
    return float(numbers[0]) if len(numbers) == 1 else None


def parse_text(text: str) -> str | None:
    if is_not_sure(text):
        return NOT_SURE
    cleaned = redact_ssn(text.strip())
    return cleaned if re.search(r"[A-Za-z]", cleaned) else None


def parse_ssn(text: str) -> tuple[str | None, bool]:
    """(practice number as 9XX-XX-XXXX or None, looks_real). A real-looking number is never returned."""
    if is_not_sure(text):
        return NOT_SURE, False
    match = _SSN_PATTERN.match(text.strip())
    if not match:
        return None, False
    if not match.group(1).startswith("9"):
        return None, True
    return "-".join(match.groups()), False


def parse_answer(question: Question, text: str):
    if question.kind == YES_NO:
        return parse_yes_no(text)
    if question.kind == CHOICE:
        return parse_choice(text, question.choices)
    if question.kind == DATE:
        return parse_date(text)
    if question.kind == AMOUNT:
        return parse_amount(text)
    return parse_text(text)


# ---- saving answers ---------------------------------------------------------------


def _with_history(name: str, new: dict, facts: dict) -> dict:
    """Keep the earlier answer in `history` when an answer changes, so nothing is lost."""
    old = facts.get(name)
    if not isinstance(old, dict):
        return new
    history = list(old.get("history", []))
    if old.get("value") != new["value"]:
        history.append({k: v for k, v in old.items() if k != "history"})
    return {**new, "history": history} if history else new


def record_answer(question: Question, value, facts: dict) -> dict:
    """The `facts` update for one answer. Never removes an earlier fact."""
    if question.part:
        dependents = [dict(d) for d in _value(facts, "dependents") or []]
        index = question.index or 0
        update = {}
        if question.part == "another":
            is_last = index >= len(dependents) - 1
            if value == "yes" and is_last:
                dependents.append({})
            elif value != "yes":
                update["dependents_complete"] = {"value": "yes", "source": "user"}
        else:
            while len(dependents) <= index:
                dependents.append({})
            person = dependents[index]
            old = person.get(question.part)
            if old is not None and old != value:
                person["history"] = [*person.get("history", []), {question.part: old}]
            person[question.part] = value
        update["dependents"] = {"value": dependents, "source": "user"}
        return update
    if question.kind == AMOUNT and value != NOT_SURE:
        new = {
            "value": value,
            "source": "direct user input",
            "entered_by": "taxpayer",
            "entered_on": datetime.now(timezone.utc).date().isoformat(),
        }
    else:
        new = {"value": value, "source": "user"}
    return {question.fact: _with_history(question.fact, new, facts)}


def update_notes(question: Question, value, reason: str | None, facts: dict) -> dict:
    """The `volunteer_notes` update, or {} if nothing changes.

    A "not sure" (or a request for a person) adds an open note for that question, once.
    A real answer given later marks the open note resolved; notes are never deleted."""
    notes = [dict(n) for n in _value(facts, NOTES) or []]
    open_note = next((n for n in notes if n["question"] == question.key and not n["resolved"]
                      and n["reason"] in (REASON_NOT_SURE, REASON_ASKED)), None)
    if value == NOT_SURE and open_note is None:
        notes.append({"question": question.key, "question_text": question.text,
                      "reason": reason or REASON_NOT_SURE, "resolved": False})
    elif value != NOT_SURE and open_note is not None:
        open_note["resolved"] = True
    else:
        return {}
    return {NOTES: {"value": notes, "source": "intake"}}


def _earlier_answer(question: Question, facts: dict) -> str | None:
    """The person's earlier answer in plain words, to remind them when going back."""
    if question.part:
        dependents = _value(facts, "dependents") or []
        if question.part == "another" or question.index >= len(dependents):
            return None
        value = dependents[question.index].get(question.part)
        if question.part == "ssn" and value not in (None, NOT_SURE):
            return "a practice number"
    else:
        value = _value(facts, question.fact)
    if value is None:
        return None
    if value == NOT_SURE:
        return "not sure"
    if question.kind == DATE:
        born = datetime.strptime(value, "%Y-%m-%d")
        return f"{born:%B} {born.day}, {born.year}"
    if question.kind == AMOUNT:
        return f"{value:,.2f}"
    return str(value).replace("_", " ")


# ---- the agent --------------------------------------------------------------------


def _latest_reply(messages: list) -> str | None:
    """The newest user message after Intake's last question, if there is one."""
    for message in reversed(messages):
        if message["role"] == "assistant":
            return None
        if message["role"] == "user":
            return message["content"]
    return None


def _ask(text: str, facts_update: dict | None = None) -> dict:
    update = {
        "messages": [{"role": "assistant", "content": text}],
        "pending_question": text,
        "handoff_request": {"to": "end", "reason": "awaiting user reply"},
    }
    if facts_update:
        update["facts"] = facts_update
    return update


def _progress(facts: dict) -> tuple[str | None, list[str]]:
    """(key of the question being asked, keys of answered questions in the order answered)."""
    progress = _value(facts, PROGRESS) or {}
    return progress.get("asking"), list(progress.get("answered", []))


def _progress_fact(asking: str | None, answered: list[str]) -> dict:
    return {PROGRESS: {"value": {"asking": asking, "answered": answered}, "source": "intake"}}


def _revisit(target: Question, opening: str, answered: list[str], facts: dict) -> dict:
    """Ask an earlier question again, reminding the person of their earlier answer."""
    earlier = _earlier_answer(target, facts)
    reminder = f" Earlier you said: {earlier}." if earlier else ""
    return _ask(f"{opening}{reminder} {target.text}", _progress_fact(target.key, answered))


def _go_back(question: Question, answered: list[str], facts: dict) -> dict:
    """Re-ask the question answered just before the current one."""
    position = answered.index(question.key) if question.key in answered else len(answered)
    if position == 0:
        return _ask(f"{GO_BACK_FIRST} {question.text}", _progress_fact(question.key, answered))
    previous = question_for_key(answered[position - 1], facts)
    return _revisit(previous, "Sure, let's go back.", answered, facts)


def safety_check(reply: str, question: Question) -> tuple[str, str, str] | None:
    """(condition, generic alarm reason, calm reply) if this message needs a human. Most serious first."""
    if mentions_pressure(reply):
        return EXPLOITATION_SIGNS, ALARM_PRESSURE, CONCERN_REPLY
    if question.id != "Q25" and someone_else_answering(reply):  # Q25 is checked as an answer
        return EXPLOITATION_SIGNS, ALARM_THIRD_PARTY, CONCERN_REPLY
    if question.id != "Q22" and mentions_spouse_died(reply):  # Q22 is checked as an answer
        return FILING_STATUS_AMBIGUITY, ALARM_SPOUSE_DIED, SPOUSE_DIED_REPLY
    if asks_for_advice(reply):
        return TAX_ADVICE_REQUEST, ALARM_ADVICE, ADVICE_REPLY
    return None


def answer_alarm(question: Question, value) -> tuple[str, str, str] | None:
    """Alarms raised by the answer itself: Q22 "yes", or a helper (Q25) with no stated permission."""
    if question.id == "Q22" and value == "yes":
        return FILING_STATUS_AMBIGUITY, ALARM_SPOUSE_DIED, SPOUSE_DIED_REPLY
    if question.id == "Q25" and not (isinstance(value, str) and has_authority(value)):
        return EXPLOITATION_SIGNS, ALARM_THIRD_PARTY, CONCERN_REPLY
    return None


def _safety_note(question: Question, reason: str, words: str, facts: dict) -> dict:
    """A note for the volunteer, with the person's own words (kept out of the alarm itself)."""
    notes = [dict(n) for n in _value(facts, NOTES) or []]
    notes.append({"question": question.key, "question_text": question.text, "reason": reason,
                  "resolved": False, "taxpayer_words": redact_ssn(words)})
    return {NOTES: {"value": notes, "source": "intake"}}


def _raise_alarm(alarm: tuple[str, str, str], facts_update: dict, intake_complete: bool = False) -> dict:
    """Say the calm reply and set the escalation flag; the orchestrator pauses for a volunteer.
    After the volunteer chooses "continue", Intake asks the question in `intake_progress` again."""
    condition, reason, reply_text = alarm
    update = {
        "messages": [{"role": "assistant", "content": reply_text}],
        "facts": facts_update,
        "pending_question": None,
        "escalation": {"pending": True, "condition": condition, "reason": reason, "raised_by": "intake"},
        "handoff_request": {"to": "human", "reason": reason},
    }
    if intake_complete:
        update["intake_complete"] = True
    return update


def run(view, tools):
    facts = dict(view.get("facts") or {})
    messages = view.get("messages") or []
    asking, answered = _progress(facts)
    question = question_for_key(asking, facts) if asking else next_question(facts)
    if question is None:
        return {"pending_question": None, "intake_complete": True,
                "handoff_request": {"to": "extraction", "reason": "intake complete"}}
    if not any(m["role"] == "assistant" for m in messages):
        return _ask(f"{WELCOME} {question.text}", _progress_fact(question.key, answered))
    reply = _latest_reply(messages)
    if reply is None:
        return _ask(question.text, _progress_fact(question.key, answered))
    alarm = safety_check(reply, question)
    if alarm:
        note = _safety_note(question, alarm[1], reply, facts)
        return _raise_alarm(alarm, {**note, **_progress_fact(question.key, answered)})
    if is_go_back(reply):
        return _go_back(question, answered, facts)
    # In a free-text answer only a short message counts ("what do you mean?"), not a long reply.
    if is_confused(reply) and (question.kind != TEXT or len(reply.split()) <= 6):
        return _ask(f"No problem. {EXPLANATIONS[question.id]} {NOT_SURE_OK} {question.text}")
    # "Actually I was married": a correction word plus an earlier topic jumps to that question.
    # Not for free-text questions, where such a sentence is usually the answer itself.
    topic = topic_of(reply, [k for k in answered if k != question.key])
    if topic and is_correction(reply) and question.kind != TEXT and not wants_volunteer(reply):
        return _revisit(question_for_key(topic, facts), "No problem, let's fix that.", answered, facts)

    reason = None
    if wants_volunteer(reply):
        value, reason = NOT_SURE, REASON_ASKED
    elif question.kind == SSN:
        value, looks_real = parse_ssn(reply)
        if looks_real:
            return _ask(f"{REAL_SSN} {question.text}")
    else:
        value = parse_answer(question, reply)
    if value is None:
        if topic:  # not an answer, but names an earlier question (e.g. "my date of birth")
            return _revisit(question_for_key(topic, facts), "No problem, let's fix that.", answered, facts)
        if is_correction(reply):
            return _ask(WHICH_ANSWER)
        return _ask(f"Sorry, I didn't quite understand. {HINTS[question.kind]} {GO_BACK_TIP} {question.text}")

    saved = {**record_answer(question, value, facts), **update_notes(question, value, reason, facts)}
    if question.key not in answered:
        answered.append(question.key)
    facts.update(saved)
    following = next_question(facts)  # first question still unanswered: carries on where we left off
    alarm = answer_alarm(question, value)
    if alarm:
        note = _safety_note(question, alarm[1], reply, facts)
        progress = _progress_fact(following.key if following else None, answered)
        return _raise_alarm(alarm, {**saved, **note, **progress}, intake_complete=following is None)
    prefix = f"{VOLUNTEER_ACK} " if reason else f"{NOT_SURE_ACK} " if value == NOT_SURE else ""
    if following is None:
        return {
            "messages": [{"role": "assistant", "content": f"{prefix}{DONE}"}],
            "facts": {**saved, **_progress_fact(None, answered)},
            "pending_question": None,
            "intake_complete": True,
            "handoff_request": {"to": "extraction", "reason": "intake complete"},
        }
    return _ask(f"{prefix}{following.text}", {**saved, **_progress_fact(following.key, answered)})
