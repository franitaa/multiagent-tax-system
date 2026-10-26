# Intake script (card INT-1)

Owner: Supriya Patil (Intake + Guardrails & ethics).

## Summary (read this first)
**What this file is:** the plan for the conversation with the taxpayer. It lists every
question Intake will ask, in order, and the exact name each answer is saved under.

**What Intake can do today:** the real Intake lives in `src/agents/intake_agent.py`. It
asks these questions one at a time, saves the answers under the names below (INT-2), and
lets the person say "go back" to change an earlier answer without losing anything (INT-3).
"I'm not sure" or "can I talk to a person?" is always accepted and noted for a volunteer
in `volunteer_notes` (INT-5).
It also listens for trouble and calls a volunteer (GRD-1, GRD-2): a request for tax
advice, a spouse who died in 2025, someone else answering without permission, or
pressure about money or the refund account. These alarms are tested against a list of
tricky messages in `tests/test_guardrails.py` (GRD-3).
A Social Security number nobody asked for is removed and never saved (INT-4); see
"Volunteered Social Security numbers" below for how and why.
It is not plugged in yet: `src/agents/intake.py` is still the placeholder that the
orchestration tests use.

**What is still missing (and the card for each):**
- Removing a volunteered SSN from the chat history itself: the chat page will do this
  before a message enters the system (INT-6)
- The large-type, screen-reader friendly chat page (INT-6)

**What teammates need from this file:**
- Eligibility & Rules and Computation: please read answers using the names in
  "Answer names" below, so we all use the same names.
- Everyone: Q24 and Q25 are new. They cover escalation condition 6 (someone else
  answering for the taxpayer).
- Eligibility & Rules (Matthew): Intake only records Q21 (can someone claim you) and Q23
  (lived in the US all year). Whether a "yes", "no" or "not sure" there makes the return
  out of scope is a tax rule, so please decide it in Rules and raise OUT_OF_SCOPE.

---

This is the list of questions the Intake agent asks, and the names it uses to save each answer.

## Rules for every question
- One question only. Never two questions in one sentence.
- Plain words. A hard term gets a short explanation the first time it appears.
- Intake only asks and records. It never does arithmetic and never explains tax rules.
- "I'm not sure" is always a valid answer. It is saved and marked for a volunteer.
- The person can say "go back" or change an earlier answer at any time. No answer is ever deleted.
- Intake does not ask for a Social Security number unless the form needs it (dependents only),
  and only accepts a practice number starting with 9 (900-999). Real-looking numbers are blocked and never stored.

## The questions

### Filing status
| # | Question | Answers | Asked when |
|---|---|---|---|
| Q1 | "On December 31, 2025, were you married?" | yes / no / not sure | always |
| Q2 | "Do you and your spouse plan to file one tax return together?" | yes / no / not sure | Q1 = yes |
| Q3 | "Which of these fits you best: single, widowed, or taking care of someone who lives with you?" | single / widowed / caring for someone / not sure | Q1 = no |

### Age and sight
| # | Question | Answers | Asked when |
|---|---|---|---|
| Q4 | "What is your date of birth? For example: March 4, 1950." | a date / not sure | always |
| Q5 | "Are you legally blind?" | yes / no / not sure | always |
| Q6 | "What is your spouse's date of birth?" | a date / not sure | Q1 = yes |
| Q7 | "Is your spouse legally blind?" | yes / no / not sure | Q1 = yes |

### Dependents
| # | Question | Answers | Asked when |
|---|---|---|---|
| Q8 | "Does anyone depend on you for support, such as a child or a relative?" | yes / no / not sure | always |
| Q9 | "What is this person's full name?" | a name | Q8 = yes |
| Q10 | "How is this person related to you?" | free text | after Q9 |
| Q11 | "Does anyone else depend on you for support?" | yes / no | after Q10 (repeat Q9-Q11 per person) |
| Q12 | "For this test, please enter a practice Social Security number that starts with 9. What is the number for [name]?" | 9XX-XX-XXXX | after Q10 (the form lists each dependent's SSN) |

### Documents
| # | Question | Answers | Asked when |
|---|---|---|---|
| Q13 | "Did you get a W-2 form from a job this year?" | yes / no / not sure | always |
| Q14 | "Did you get a Social Security benefits statement, called an SSA-1099?" | yes / no / not sure | always |
| Q15 | "Did you get a form for money paid out of a pension or retirement account, called a 1099-R?" | yes / no / not sure | always |
| Q16 | "Did you get a form showing bank interest, called a 1099-INT?" | yes / no / not sure | always |
| Q17 | "Did you get a form showing dividends, called a 1099-DIV?" | yes / no / not sure | always |

### Payments and adjustments
| # | Question | Answers | Asked when |
|---|---|---|---|
| Q18 | "During 2025, did you send any tax payments to the IRS yourself?" | yes / no / not sure | always |
| Q19 | "About how much did you send in total?" | an amount / not sure | Q18 = yes |
| Q20 | "Do you have any adjustments to your income that you want to include?" | yes / no / not sure | always |
| Q20a | "What is the total amount of those adjustments?" | an amount / not sure | Q20 = yes |

Amounts from Q19 and Q20a are recorded as "direct user input" (who and when), as the brief allows.
Intake does not check or add them up.

### Safety questions (each one can send the case to a human)
| # | Question | Answers | Goes to a human when |
|---|---|---|---|
| Q21 | "Can another person claim you as a dependent on their tax return?" | yes / no / not sure | yes or not sure |
| Q22 | "Did a spouse pass away during 2025?" | yes / no | yes (FILING_STATUS_AMBIGUITY) |
| Q23 | "Did you live in the United States for all of 2025?" | yes / no / not sure | no or not sure |
| Q24 | "Are you answering these questions yourself today?" | yes / no | see Q25 |
| Q25 | "Who is helping you, and are they allowed to act for you, for example with a power of attorney?" | free text | Q24 = no and no permission is stated (EXPLOITATION_SIGNS) |

## Always-available phrases
- "I'm not sure": "That's okay. I'll note this for a volunteer to help with."
- Asking for advice: "I'm here to help fill in your tax form, so I can't give tax advice. I'll note your question for the volunteer."
- "Go back": repeat the previous question and keep the earlier answer until a new one is given.

## Volunteered Social Security numbers (card INT-4): how and why
The brief asks us not to collect an SSN we do not need, and to handle one deliberately
if it is offered anyway. Intake asks for an SSN in exactly one place: Q12, a practice
number for each dependent, because the form lists one.

**What Intake does when someone types an SSN it did not ask for** (for example, at
"Were you married?" they type "No, and my number is 123-45-6789"):
1. It removes the number from the message before anything else reads it, so it can
   never reach the answers, the volunteer notes, or the safety alarms.
2. It still uses the rest of the message. "No, and my number is ..." is saved as "no".
3. It says kindly: "Thank you, but I don't need a Social Security number here, so I did
   not save it." If the number looked real (not starting with 9), it adds: "To keep you
   safe, please don't type your real number in this chat."
4. If the message was only a number, it asks the same question again.

**What happens at Q12 (when Intake does ask):** only practice numbers starting with 9
(900-999) are accepted. A real-looking number is refused, never saved, and never
repeated back.

**Why we chose this:**
- *Collect only what we need.* A number given at the wrong moment is not needed for any
  line of the form, so even a practice number is not kept there.
- *Never punish the person.* Older taxpayers may share an SSN out of habit or trust.
  Intake thanks them, explains in one sentence, and keeps the rest of their answer, so
  they do not have to start again or feel they did something wrong.
- *Safe by default.* Removing the number first means no later step can accidentally
  store or log it. Alarm reasons are generic and traces store only field names.

**Known limit:** the person's own message is still kept in the chat history, because
the system adds it before Intake runs. The chat page (INT-6) will remove the number
before the message is sent in, so it is never stored at all.

## Answer names (shared contract for `facts`)
Every answer is saved in `facts` as `{"value": ..., "source": "user"}`.
Other agents should read these names. Please tell Supriya before renaming one.

| Fact name | From | Value |
|---|---|---|
| `married_dec31` | Q1 | `"yes"` / `"no"` / `"not_sure"` |
| `file_jointly` | Q2 | `"yes"` / `"no"` / `"not_sure"` |
| `household_situation` | Q3 | `"single"` / `"widowed"` / `"caring_for_someone"` / `"not_sure"` |
| `taxpayer_birth_date` | Q4 | `"YYYY-MM-DD"` or `"not_sure"` |
| `taxpayer_blind` | Q5 | `"yes"` / `"no"` / `"not_sure"` |
| `spouse_birth_date` | Q6 | `"YYYY-MM-DD"` or `"not_sure"` |
| `spouse_blind` | Q7 | `"yes"` / `"no"` / `"not_sure"` |
| `has_dependents` | Q8 | `"yes"` / `"no"` / `"not_sure"` |
| `dependents` | Q9-Q12 | list of `{"name", "relationship", "ssn"}` (ssn is 9XX-XX-XXXX only) |
| `has_w2` ... `has_1099_div` | Q13-Q17 | `"yes"` / `"no"` / `"not_sure"` (`has_w2`, `has_ssa_1099`, `has_1099_r`, `has_1099_int`, `has_1099_div`) |
| `made_estimated_payments` | Q18 | `"yes"` / `"no"` / `"not_sure"` |
| `estimated_payments_amount` | Q19 | number, `source: "direct user input"` |
| `has_adjustments` | Q20 | `"yes"` / `"no"` / `"not_sure"` |
| `adjustments_amount` | Q20a | number, `source: "direct user input"` |
| `can_be_claimed_as_dependent` | Q21 | `"yes"` / `"no"` / `"not_sure"` |
| `spouse_died_2025` | Q22 | `"yes"` / `"no"` |
| `us_resident_all_year` | Q23 | `"yes"` / `"no"` / `"not_sure"` |
| `answering_for_self` | Q24 | `"yes"` / `"no"` |
| `helper_description` | Q25 | free text |

Extra entries:
- `history`: if the person changes an answer, the earlier one is kept in that fact's
  `history` list (for a dependent, in that person's own `history`). Nothing is deleted.
- `volunteer_notes`: a list of questions a volunteer should help with, one note per
  question: `{"question", "question_text", "reason", "resolved"}`. `reason` is
  "taxpayer not sure" or "taxpayer asked for a person". If the person answers later, the
  note is marked `resolved: true`, never deleted. The dashboard can show these.
- `dependents_complete`: `"yes"` once the person says nobody else depends on them.
- `intake_progress`: Intake's own bookkeeping (which question it is asking, and the
  order of answers, for "go back"). Other agents can ignore it.
- If an answer changes so that some questions no longer apply (e.g. "married" becomes
  "not married"), the old answers to those questions are kept. Rules should only use
  answers whose question applies.

`filing_status` is NOT written by Intake: working out the filing status is a tax rule, so
Eligibility & Rules decides it from the answers above, and a volunteer may set it through
the human gate (source `human:FILING_STATUS_AMBIGUITY`).

## Decisions taken (no instructor Q&A available)
- Q12: the brief lists dependents' SSNs on the form, so Intake asks for one per dependent,
  practice numbers only.
- Q20: line 10 is "Schedule 1, line 26", and the brief says Schedules 1-3 are "user just
  directly inputs values". So Intake asks for one total amount and records it as direct user input.
