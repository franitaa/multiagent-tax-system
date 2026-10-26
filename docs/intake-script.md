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

The taxpayer chat page (INT-6) is in `src/ui/`: run `streamlit run src/ui/taxpayer_chat.py`.
It has large text, screen-reader labels, a case ID to continue later, a "Your answers so
far" list with Change buttons, and it removes real-looking SSNs before a message is sent in.

**What is still missing:**
- Permanent session storage: sessions last while the app runs, until Shruti's
  checkpointer is plugged in (one place: `chat_session.make_graph()`).

**What teammates need from this file:**
- Eligibility & Rules and Computation: please read answers using the names in
  "Answer names" below, so we all use the same names.
- Everyone: Q24 and Q25 are new. They cover escalation condition 6 (someone else
  answering for the taxpayer).
- Eligibility & Rules (Matthew): Intake only records Q21 (can someone claim you) and Q23
  (lived in the US all year). Whether a "yes", "no" or "not sure" there makes the return
  out of scope is a tax rule, so please decide it in Rules and raise OUT_OF_SCOPE.
  The same goes for the new screening answers (Q17a-Q17e: other forms, sales, business or
  rental income, money abroad, digital assets), `spouse_itemizing` (Q2c),
  `spouse_can_be_claimed` (Q21b) and `spouse_death_year` (Q3a).

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
| Q0 | "What is your full name?" | free text | always (first question) |
| Q1 | "On December 31, 2025, were you married?" | yes / no / not sure | always |
| Q2 | "Do you and your spouse plan to file one tax return together?" | yes / no / not sure | Q1 = yes |
| Q2b | "What is your spouse's full name?" | free text | Q2 = yes |
| Q2c | "Will your spouse list their deductions one by one on their own tax return, instead of taking the standard amount?" | yes / no / not sure | married and Q2 = no |
| Q3 | "Which of these fits you best: single, widowed, or taking care of someone who lives with you?" | single / widowed / caring for someone / not sure | Q1 = no |
| Q3a | "In what year did your husband or wife pass away?" | a year / not sure | Q3 = widowed and Q8 = yes (asked after the dependents) |

### Age and sight
| # | Question | Answers | Asked when |
|---|---|---|---|
| Q4 | "What is your date of birth? Please type the month as a word, then the day and the year, for example: March 4, 1950." | a date / not sure (read back to confirm) | always |
| Q5 | "Are you legally blind?" | yes / no / not sure | always |
| Q6 | "What is your spouse's date of birth? Please type the month as a word, then the day and the year, for example: June 1, 1952." | a date / not sure (read back to confirm) | Q1 = yes |
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
| Q17a | "Did you get any other tax forms for 2025, such as a 1099-NEC, 1099-MISC or 1099-B?" | yes / no / not sure | always |
| Q17b | "During 2025, did you sell any stocks, funds or property?" | yes / no / not sure | always |
| Q17c | "During 2025, did you earn money from your own business, freelance work, or renting out property?" | yes / no / not sure | always |
| Q17d | "During 2025, did you have any income, bank accounts or investments outside the United States?" | yes / no / not sure | always |
| Q17e | "During 2025, did you receive, sell or trade any digital assets, such as cryptocurrency?" | yes / no / not sure | always |

### Payments and adjustments
| # | Question | Answers | Asked when |
|---|---|---|---|
| Q18 | "During 2025, did you send any tax payments to the IRS yourself?" | yes / no / not sure | always |
| Q19 | "About how much did you send in total?" | an amount / not sure | Q18 = yes |
| Q20 | "Do you have any adjustments to your income that you want to include?" | yes / no / not sure | always |
| Q20a | "What is the total amount of those adjustments?" | an amount / not sure | Q20 = yes |
| Q20b | "If you get a refund, would you like it paid into a bank account or sent as a paper check?" | bank account / paper check / not sure | always |
| Q20c | "Is that bank account in your own name? An account you share with your spouse counts as yes." | yes / no / not sure | Q20b = bank account; no or not sure goes to a human (EXPLOITATION_SIGNS) |

Amounts from Q19 and Q20a are recorded as "direct user input" (who and when), as the brief allows.
Intake does not check or add them up.

### Safety questions (each one can send the case to a human)
| # | Question | Answers | Goes to a human when |
|---|---|---|---|
| Q21 | "Can another person claim you as a dependent on their tax return?" | yes / no / not sure | yes or not sure |
| Q21b | "Can another person claim your spouse as a dependent on their tax return?" | yes / no / not sure | Q1 = yes (recorded for Rules) |
| Q22 | "Did a spouse pass away during 2025?" | yes / no | yes (FILING_STATUS_AMBIGUITY) |
| Q23 | "Did you live in the United States for all of 2025?" | yes / no / not sure | no or not sure |
| Q24 | "Are you answering these questions yourself today?" | yes / no | see Q25 |
| Q25 | "Who is helping you, and are they allowed to act for you, for example with a power of attorney?" | free text | Q24 = no and no permission is stated (EXPLOITATION_SIGNS) |

## Dates are always confirmed
People write dates in many ways, and in some countries the day comes first. So Intake is
forgiving about how a date is typed ("dec, 4,1950" works), but it always reads the date
back with the month spelled out ("Just to check: you were born on December 4, 1950. Is
that right?") and saves it only after "yes". If the date is only numbers and could mean
two dates (03/04/1950 is March 4 in the US but 3 April elsewhere), Intake does not guess:
it asks the person to type the month as a word.

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
3. It tells the person kindly what happened, instead of removing it silently (wording
   suggested by Francesca): "I removed a number that looked like a real Social Security
   number, to keep you safe. I did not save it, and I don't need one here. For this
   practice system, please only use test numbers that start with 9." A practice number
   given at the wrong moment gets: "Thank you, but I don't need a Social Security number
   here, so I did not save it."
4. If the message was only a number, it asks the same question again.

**What happens at Q12 (when Intake does ask):** only practice numbers starting with 9
(900-999) are accepted. A real-looking number is refused, never saved, and never
repeated back.

**One shared rule:** "is this a practice number?" is always decided by the Security
owner's validator, `is_fake_ssn()` in `security.py`, so the team has only one rule to
maintain. Intake only finds SSN-shaped numbers in a sentence and joins the digits first,
so "912 34 5678" is checked the same as "912-34-5678".

**Why we chose this:**
- *Collect only what we need.* A number given at the wrong moment is not needed for any
  line of the form, so even a practice number is not kept there.
- *Never punish the person.* Older taxpayers may share an SSN out of habit or trust.
  Intake thanks them, explains in one sentence, and keeps the rest of their answer, so
  they do not have to start again or feel they did something wrong.
- *Safe by default.* Removing the number first means no later step can accidentally
  store or log it. Alarm reasons are generic and traces store only field names.

**On the chat page (INT-6):** a real-looking number is removed from the message before
it is sent into the system, so it is never stored or logged at all, not even in the chat
history. Intake sees "[number removed]" and still tells the person kindly what happened.
Practice numbers (900-999) are kept, because Q12 needs them. Intake uses no AI model, so
nothing is ever sent to one.

## Answer names (shared contract for `facts`)
Every answer is saved in `facts` as `{"value": ..., "source": "user"}`.
Other agents should read these names. Please tell Supriya before renaming one.

| Fact name | From | Value |
|---|---|---|
| `taxpayer_name` | Q0 | free text |
| `married_dec31` | Q1 | `"yes"` / `"no"` / `"not_sure"` |
| `spouse_name` | Q2b | free text |
| `spouse_itemizing` | Q2c | `"yes"` / `"no"` / `"not_sure"` |
| `spouse_death_year` | Q3a | a year as a number (e.g. `2023`) or `"not_sure"` |
| `file_jointly` | Q2 | `"yes"` / `"no"` / `"not_sure"` |
| `household_situation` | Q3 | `"single"` / `"widowed"` / `"caring_for_someone"` / `"not_sure"` |
| `taxpayer_birth_date` | Q4 | `"YYYY-MM-DD"` or `"not_sure"` |
| `taxpayer_blind` | Q5 | `"yes"` / `"no"` / `"not_sure"` |
| `spouse_birth_date` | Q6 | `"YYYY-MM-DD"` or `"not_sure"` |
| `spouse_blind` | Q7 | `"yes"` / `"no"` / `"not_sure"` |
| `has_dependents` | Q8 | `"yes"` / `"no"` / `"not_sure"` |
| `dependents` | Q9-Q12 | list of `{"name", "relationship", "ssn"}` (ssn is 9XX-XX-XXXX only) |
| `has_w2` ... `has_1099_div` | Q13-Q17 | `"yes"` / `"no"` / `"not_sure"` (`has_w2`, `has_ssa_1099`, `has_1099_r`, `has_1099_int`, `has_1099_div`) |
| `has_other_tax_forms`, `sold_stocks_or_property`, `business_or_rental_income`, `foreign_income_or_accounts`, `digital_assets` | Q17a-Q17e | `"yes"` / `"no"` / `"not_sure"` |
| `made_estimated_payments` | Q18 | `"yes"` / `"no"` / `"not_sure"` |
| `estimated_payments_amount` | Q19 | number, `source: "direct user input"` |
| `has_adjustments` | Q20 | `"yes"` / `"no"` / `"not_sure"` |
| `adjustments_amount` | Q20a | number, `source: "direct user input"` |
| `refund_method` | Q20b | `"bank_account"` / `"paper_check"` / `"not_sure"` |
| `refund_account_own_name` | Q20c | `"yes"` / `"no"` / `"not_sure"` |
| `can_be_claimed_as_dependent` | Q21 | `"yes"` / `"no"` / `"not_sure"` |
| `spouse_can_be_claimed` | Q21b | `"yes"` / `"no"` / `"not_sure"` |
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
- Possible exploitation is "stop" only (agreed with Francesca): the brief says notice and
  stop, not judge. The message to the taxpayer stays gentle and never accuses anyone; the
  volunteer's note records why. If a helper really is authorised (for example a daughter
  with power of attorney), the volunteer sorts it out outside the system.
  *Future improvement:* let a volunteer restart the case with the authority documented.
- Names and SSNs at the top of the form: the brief only requires dependents' SSNs (3.1) and
  says not to ask for SSNs we do not need (4.3). So Intake asks for the taxpayer's name
  (and the spouse's name on a joint return), but never for the taxpayer's or spouse's SSN.
  The case ID identifies the session.
- Bank details: Intake asks only whether the refund account is in the person's own name,
  never for account or routing numbers.
- Q12: the brief lists dependents' SSNs on the form, so Intake asks for one per dependent,
  practice numbers only.
- Q20: line 10 is "Schedule 1, line 26", and the brief says Schedules 1-3 are "user just
  directly inputs values". So Intake asks for one total amount and records it as direct user input.
