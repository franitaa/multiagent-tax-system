"""Intake agent (real version). Owner: Supriya Patil.

SUMMARY FOR THE TEAM
What it does today (card INT-2):
  - Talks to the taxpayer, one question at a time, using the script in docs/intake-script.md.
  - Skips questions that do not apply (no spouse questions for someone not married, etc.).
  - Understands simple answers: yes / no / not sure, a choice, a date, a name, an amount.
  - If it does not understand an answer, it says so kindly and asks the same question again.
  - Saves every answer in `facts` under the shared names listed in docs/intake-script.md.
  - Amounts (estimated payments, adjustments) are saved as "direct user input" with who and when.
  - Only accepts practice Social Security numbers starting with 9. A real-looking number is
    refused, never saved in `facts`, and never repeated back.
  - Never does arithmetic and never explains tax rules. It only asks and records.
  - When the last question is answered it marks intake complete and hands over to Extraction.

What is still missing:
  - "Go back" and changing an earlier answer (INT-3).
  - Fuller handling of a volunteered SSN: the user's own message still sits in the chat
    history (INT-4).
  - Raising a volunteer flag for "not sure" answers; today they are only saved (INT-5).
  - The chat page (INT-6) and the safety flags: advice, spouse died, pressure (GRD-1 to GRD-3).

Not plugged in yet: src/agents/intake.py is still the 2-message placeholder that the
orchestration tests rely on. Once those tests use their own fake Intake, intake.py will
point here.
"""
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

NOT_SURE = "not_sure"

YES_NO = "yes_no"
CHOICE = "choice"
DATE = "date"
TEXT = "text"
AMOUNT = "amount"
SSN = "ssn"

WELCOME = (
    "Hello. I will ask you some questions about your 2025 taxes, one at a time. "
    "There are no wrong answers, and you can say \"I'm not sure\" at any time."
)
NOT_SURE_ACK = "That's okay. I've noted that you're not sure."
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


def _dependent_question(facts: dict) -> Question | None:
    """Q9-Q12 repeat for each dependent; Q11 asks whether there is another one."""
    if _value(facts, "has_dependents") != "yes" or _value(facts, "dependents_complete") == "yes":
        return None
    dependents = _value(facts, "dependents") or []
    current = dependents[-1] if dependents else {}
    if "name" not in current:
        return Question("Q9", "dependents", TEXT, "What is this person's full name?", part="name")
    name = current["name"] if current["name"] != NOT_SURE else "this person"
    if "relationship" not in current:
        return Question("Q10", "dependents", TEXT, f"How is {name} related to you?", part="relationship")
    if "ssn" not in current:
        return Question(
            "Q12", "dependents", SSN,
            f"For this test, please use a practice Social Security number that starts with 9. "
            f"What is the practice number for {name}?",
            part="ssn",
        )
    return Question("Q11", "dependents", YES_NO, "Does anyone else depend on you for support?",
                    part="another")


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
    cleaned = text.strip()
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


def record_answer(question: Question, value, facts: dict) -> dict:
    """The `facts` update for one answer. Never removes an earlier fact."""
    if question.part:
        dependents = [dict(d) for d in _value(facts, "dependents") or []]
        if question.part == "name":
            if dependents and "name" not in dependents[-1]:
                dependents[-1]["name"] = value
            else:
                dependents.append({"name": value})
        elif question.part == "another":
            if value == "yes":
                dependents.append({})
            else:
                return {
                    "dependents": {"value": dependents, "source": "user"},
                    "dependents_complete": {"value": "yes", "source": "user"},
                }
        else:
            dependents[-1][question.part] = value
        return {"dependents": {"value": dependents, "source": "user"}}
    if question.kind == AMOUNT and value != NOT_SURE:
        return {
            question.fact: {
                "value": value,
                "source": "direct user input",
                "entered_by": "taxpayer",
                "entered_on": datetime.now(timezone.utc).date().isoformat(),
            }
        }
    return {question.fact: {"value": value, "source": "user"}}


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


def run(view, tools):
    facts = dict(view.get("facts") or {})
    messages = view.get("messages") or []
    question = next_question(facts)
    if question is None:
        return {"pending_question": None, "intake_complete": True,
                "handoff_request": {"to": "extraction", "reason": "intake complete"}}
    if not any(m["role"] == "assistant" for m in messages):
        return _ask(f"{WELCOME} {question.text}")
    reply = _latest_reply(messages)
    if reply is None:
        return _ask(question.text)

    if question.kind == SSN:
        value, looks_real = parse_ssn(reply)
        if looks_real:
            return _ask(f"{REAL_SSN} {question.text}")
    else:
        value = parse_answer(question, reply)
    if value is None:
        return _ask(f"Sorry, I didn't quite understand. {HINTS[question.kind]} {question.text}")

    saved = record_answer(question, value, facts)
    facts.update(saved)
    following = next_question(facts)
    prefix = f"{NOT_SURE_ACK} " if value == NOT_SURE else ""
    if following is None:
        return {
            "messages": [{"role": "assistant", "content": f"{prefix}{DONE}"}],
            "facts": saved,
            "pending_question": None,
            "intake_complete": True,
            "handoff_request": {"to": "extraction", "reason": "intake complete"},
        }
    return _ask(f"{prefix}{following.text}", saved)
