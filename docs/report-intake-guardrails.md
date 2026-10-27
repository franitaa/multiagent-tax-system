# Report section: Intake agent and Guardrails & ethics

Owner: Supriya Patil. Draft for the team's five-page report (card REP-1).

## Summary (read this first)
**What this section covers:** how the Intake agent talks to an older taxpayer, the design
choices behind it (assignment §4.3), and the safety alarms that send a case to a human
volunteer (§4.4, Guardrails & ethics).
**Status:** everything described here is built and tested (about 490 automated tests in the team suite). Still
open: permanent session storage (Memory owner) and switching the main graph from the
placeholder Intake to the real one (after the Phase 3 merge).

---

## 1. Role of the Intake agent
Intake is the only agent that talks to the taxpayer. It asks questions, records the
answers in the shared state (`facts`), and hands over to Document Extraction when it is
finished. Following the brief, it **never does arithmetic and never interprets tax rules**:
for example, it records "married on December 31: yes" and "one return together: yes",
but the Eligibility & Rules agent decides the filing status. Every amount the taxpayer
types (estimated payments, adjustments) is stored as "direct user input" with who
entered it and when, as §4.2 allows.

Intake follows the team's handoff contract: it reads and writes only the fields it is
allowed to, asks one question per graph call (`pending_question`), and never stops the
graph itself. When something needs a human, it sets an escalation flag and the
Orchestrator performs the LangGraph interrupt.

**Design choice: plain code, not a language model.** Intake's questions, answer parsing
and safety checks are deterministic Python. This makes it impossible for Intake to give
tax advice or invent a number, keeps every behaviour testable, and costs nothing to run.
The trade-off is that unusual wording can be missed; in that case Intake falls back to
asking again or offering a volunteer, which is the safe direction.

## 2. Conversation structure
About 30 questions (fewer apply to most people) are grouped into six parts, like the
sections of an application form: *Personal information; Age and eyesight; People who
depend on you; Your income and tax forms; Payments and your refund; A few final checks.*
Questions that do not apply are skipped automatically (a person who is not married never
sees the spouse questions). The chat page shows a progress list with each part's status
in words ("Done", "In progress", "1 skipped") and labels the current question in words,
e.g. "Part 1 – Personal information – Question 3", with the question itself as the
largest text on the page.

The question list was checked against the brief and extended to collect facts other
agents need: screening questions for out-of-scope items (other 1099 forms, sales of
stocks or property, business or rental income, money abroad, digital assets), and the
refund method. Intake only records these; Rules decides whether they are in scope.

## 3. Accessibility and dignity (§4.3): design choices
All six areas in the brief were addressed.

| Area | What we built | Why |
|---|---|---|
| **One question at a time** | Every message asks exactly one question; follow-ups only appear when they apply. | Tired or anxious users should never have to answer two things at once. |
| **Plain language** | Forms are glossed in the question itself ("a Social Security benefits statement, called an SSA-1099"). "I don't understand" gives a one-sentence explanation of that question, never of a tax rule. | Understanding the question matters more than learning tax terms. |
| **Repetition and drift** | "Go back" any number of times; simple corrections ("actually I was married") jump to that question; Change buttons next to every earlier answer. A changed answer is saved and the old one kept in `history`; Intake then carries on where the person left off. | §4.3 says losing answers is a failure, so no answer is ever deleted. |
| **No unnecessary personal information** | Intake asks for names but never for the taxpayer's or spouse's SSN (§3.1 only requires dependents' SSNs) and never for bank account numbers. An SSN typed when not asked is removed before anything reads it, and the person is told kindly. | Collect only what the form needs; see section 5. |
| **Resumability** | Each session has an easy case ID (e.g. SF-482-735) used as the LangGraph thread ID. Continuing shows "Welcome back. So far we've covered: ...". | Someone who stops on Tuesday can carry on on Friday without starting again. |
| **Honest uncertainty** | "I'm not sure" (and "I can't remember", "I don't know") is always accepted and noted for a volunteer; "Skip for now" sets a question aside until the end. Nothing is left blank: a question skipped twice is noted for a volunteer. | Not knowing is a valid answer, not a failure. |

The chat page itself uses large text (22px and up), strong contrast, large buttons with a
visible keyboard focus outline, visible labels instead of grey placeholder text, and plain
text speaker labels so screen readers announce who is speaking. Dates use three labelled
boxes (Month / Day / Year, where typing "3" or "mar" both find March) because people write
dates in different orders; every date is read back for confirmation ("Just to check: you
were born on March 4, 1950. Is that right?"), a date that could mean two days (03/04/1950)
is never guessed, and a day that does not exist (April 31) is caught with a clear reason.

## 4. Guardrails: when Intake calls a human (§4.4)
Every reply is checked before anything else. When a check matches, Intake replies
calmly, writes a note for the volunteer with the person's own words, and raises the flag;
the Orchestrator then pauses the graph for a volunteer.

| Situation | Example | Condition raised |
|---|---|---|
| Request for tax advice | "Should I convert my IRA to a Roth?" | `TAX_ADVICE_REQUEST`, with "I'm here to help fill in your tax form, so I can't give tax advice. I'll note your question for the volunteer." |
| Spouse died during 2025 | Q22 answered "yes", or "my husband passed away in March" | `FILING_STATUS_AMBIGUITY` |
| Someone else answering without permission | "I'm typing for my mom", or a helper with no stated power of attorney | `EXPLOITATION_SIGNS` |
| Pressure or an unfamiliar refund account | "He told me to send the refund to his account"; refund account not in the taxpayer's name | `EXPLOITATION_SIGNS` |

**Ethical choices.** The message to the taxpayer never accuses anyone, because the helper
may be sitting next to them ("Thank you for telling me. Before we go on, I'm going to ask a
volunteer to look at this with you."). The flag carries only a generic reason, so no
personal words reach the logs; the person's words go only to the volunteer note. In line
with the brief ("notice and stop, not adjudicate"), possible exploitation can only be
stopped, not continued, by the volunteer; the team agreed a future improvement would let
a volunteer restart a case once the helper's authority is documented. Questions that need
a tax rule to judge (can someone claim you, did you live in the US all year) are only
recorded, and Rules decides.

## 5. Social Security numbers: how and why
The brief requires that only test numbers (900-999) are accepted and that a volunteered
number is handled deliberately. Intake asks for an SSN in one place only: a practice
number for each dependent. Whether a number is a practice number is always decided by
the Security owner's shared validator (`is_fake_ssn`), so the team has one rule.

If someone types an SSN where it was not asked, the chat page removes a real-looking
number **before the message enters the system**, so it is never stored or logged, and
Intake removes any other SSN-shaped number before reading the reply. Intake then tells the
person what happened instead of removing it silently: "I removed a number that looked
like a real Social Security number, to keep you safe. I did not save it, and I don't need
one here." The rest of their answer still counts, so they do not have to start again.
The reasons: collect only what is needed; never make the person feel they did something
wrong; and remove the number first so no later step can store it by accident.

## 6. Testing
About 490 automated tests across the team suite (no network or model calls; Intake's own tests are the bulk) cover answer parsing, every question
path, go back and corrections, skipping, date checks, SSN handling, the chat page (driven
through Streamlit's test runner) and full conversations through the real LangGraph
orchestrator, including a volunteer pausing and resuming or stopping a case. A separate
adversarial set (`tests/test_guardrails.py`) has 20 tricky messages that must raise the
right alarm (disguised advice, indirect pressure, "ignore your instructions...", ALL CAPS)
and 15 innocent ones that must not; its first run found 11 misses and 3 false alarms,
which were then fixed. A teammate's review later found that realistic pressure phrasings
("making me do this", "keeps my refund", "not to tell anyone") were still missed, because
the check used exact phrases. It now recognises patterns (who *keeps / takes / controls*
*my* refund or money, being *forced*, being told *not to tell anyone*), and the set grew to
53 messages that must raise an alarm and 38 innocent ones that must not ("my daughter is
making me lunch", "the bank keeps my statements", "my wife is scared of dogs"). The alarm
messages now also cover someone changing the person's bank details or holding their
passwords and ID, being told what to say, fear of a named person, and common scams aimed at
older people ("pay the IRS with gift cards", "wire money").

## 7. Failure modes and limits
- **Keyword matching can miss unusual wording** or, rarely, raise an alarm on an innocent
  sentence. A missed answer leads to a polite re-ask, at most three times: after that,
  Intake says "Let's not worry about this one" and notes the question for a volunteer, so
  nobody is stuck in a loop. A false alarm leads to a volunteer check. Both fail towards
  the safe side.
- **Sessions are kept in memory** until the team's permanent checkpointer is connected;
  a restart of the app currently loses open sessions.
- **Free-text answers** (names, the helper's description) are stored as typed; a
  volunteer reviews them.
- **Answers that stop applying** after a change (for example spouse details after
  "married" becomes "not married") are kept for the audit trail; Rules must use only
  answers whose question applies (documented in `docs/answer-names.md`).
