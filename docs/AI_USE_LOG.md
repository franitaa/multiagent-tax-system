# AI use log

One entry per working session: who, what the AI helped with, and what the person decided
or checked themselves. This feeds the AI-use disclosure paragraph (docs/AI_DISCLOSURE.md).

## Supriya Patil — Sun Oct 25, 2026 (evening, ~6 hours)
**Tool:** Claude Code (Claude Opus 5.5) in VS Code, working only on my branch `feature/intake-agent`.

**What the AI helped with**
- Read the assignment, team plan and repo, and explained in plain words what Francesca's
  orchestrator already does and which cards are mine (Intake + Guardrails).
- Reviewed Francesca's Phase 3 branch: ran her 124 tests and read the diff. I wrote and
  sent the review questions myself (after asking for a softer wording).
- Turned my intake question list (INT-1) into `docs/intake-script.md`, and proposed the
  shared answer names and two safety questions (Q24, Q25) for escalation condition 6.
- Wrote the Intake agent code and tests (`src/agents/intake_agent.py`,
  `tests/test_intake_agent.py`, `tests/test_guardrails.py`): one question at a time,
  answer parsing, go back and simple corrections (INT-3), plain-words explanations,
  volunteer notes for "not sure" (INT-5), and the safety alarms for advice, a spouse who
  died, someone else answering, and pressure (GRD-1, GRD-2, GRD-3).
- Drafted commit messages and ran git (branch, commit, push) after I approved each step.

**What I decided or checked myself**
- Approved every question, the plain-words explanations, and every sentence the
  taxpayer sees before it was committed.
- Spotted that a person might say "I was married" without knowing about "go back", and
  that "I didn't understand" got the wrong reply; both were fixed at my request.
- Chose to keep Intake in its own file so Francesca's tests are not broken, and to ask
  her before plugging it in.
- Decided Intake only records Q21/Q23 and leaves the scope decision to the Rules owner.
- Asked for a short plain-English summary at the top of every file I propose.

**How the AI's work was verified**
- All tests run before every commit (215 passing at the end), including runs through the
  real LangGraph orchestrator and a check against Francesca's Phase 3 branch.
- The adversarial tests (GRD-3) found 11 missed messages and 3 false alarms in the
  AI's first version of the alarms; these were fixed and re-tested.

**Limits I am aware of**
- The alarms use keyword matching, not AI, so unusual wording can be missed.
- Commits are marked "Co-Authored-By: Claude" to be transparent about AI help.

## Supriya Patil — Mon Oct 26, 2026 (~5 hours)
**Tool:** Claude Code (Claude Opus 5.5) in VS Code, on my branch `feature/intake-agent`
(plus a small separate branch `docs/answer-names` for PR #8).

**What the AI helped with**
- INT-4: removing a Social Security number nobody asked for, and the "how and why"
  section for the report.
- INT-6: the Streamlit chat page (`src/ui/`), with its logic kept separate and tested.
- Reviewing the assignment against my question list; it suggested missing questions
  (other forms, sales, business income, money abroad, digital assets, the refund
  account, spouse questions) and checked what the brief says about SSNs.
- Code and tests for: date read-back and day/month checks, Change buttons, the 6 parts,
  progress list and "Skip for now".
- Acting on Francesca's review: switching to Sahana's shared `is_fake_ssn()` and telling
  the person when a number was removed. Merging the latest main into my branch.
- Re-checking Francesca's Phase 3 pull request before I approved it (merged with main,
  ran all tests, read her doc changes), and drafting PR #8 (shared answer names).
- Explaining GitHub steps (approving a review, opening a pull request) and drafting my
  messages to teammates in simpler words.

**What I decided or checked myself**
- Tested the chat page in my browser and found real problems: "dec, 4,1950" was not
  understood; April 31 was accepted by the date boxes; "Question 1.1" was bigger than the
  part heading; the numbering pulled focus away from the question. All fixed at my request.
- Asked for: a way to jump from question 10 back to question 3 (Change buttons); a date
  confirmation, because some people write the day first; a month list where typing "3"
  finds March; sections like an application form; "Skip for now"; more ways to say
  "I don't know" ("I can't remember", "I forgot").
- Chose the wording and layout: "Part 1 – Personal information – Question 3" instead of
  1.1-style numbers, and "Personal information" as the first part's name.
- Decided which new questions to add (and limited the spouse's year of death to widowed
  people with dependents), to ask for names, and not to ask for the taxpayer's or
  spouse's SSN (brief §3.1 and §4.3).
- Agreed with Francesca: exploitation stays "stop" only, and her tests will use a pretend
  Intake so my real one can be switched on.

**How the AI's work was verified**
- All tests run before every commit (326 passing at the end), including a test that
  fills in the real page's date boxes and one that checks April 31 is never sent.
- Tests caught AI mistakes before they were committed: a scrambled line of code (twice,
  from a backslash problem when saving), and a part wrongly shown as "Done" while a
  question in it was still skipped.

**Limits I am aware of**
- Sessions are kept only while the app runs until Shruti's saved-session store is plugged in.
- My real Intake is not switched on in the main system yet (waiting for Phase 3 to merge).

### Supriya Patil — Mon Oct 26, 2026 (afternoon addition, ~1.5 hours)
**What the AI helped with**
- Drafted my report section (`docs/report-intake-guardrails.md`) from the work and notes
  already in the repo; I read it before it was saved.
- Before opening my pull request: merged the latest main into my branch and ran every
  team test together (427 passing), then drafted the PR description (PR #9).
- Compared the new Rules agent with my Intake and found that they use different answer
  names, and that Intake's "no" would be read as true for blindness.

**What I decided or checked myself**
- Asked whether the mismatch meant redoing my work; decided to keep the team's shared
  names (PR #8) and asked Matthew to align Rules, while accepting that yes/no/not sure and
  "no filing status from Intake" cannot change because of the brief.
- Worked out what I needed to tell the team, in a clear and simple form (which answer
  names differ, why yes/no/not sure must stay, and why Intake cannot send a filing
  status), then sent the messages to Matthew and Francesca.
- Chose a shorter, simpler PR description and opened PR #9 myself.

## Sahana (Person 5: Computation, provenance, security)
**Tool:** Claude Code (Claude Sonnet 5.5) in VS Code, on my branch `p5-integrated`.

**What the AI helped with**
- Inspected the repo and found that the Computation agent in the graph was still a stub and
  that no draft form showed provenance. It wrote the real agent (`src/agents/computation.py`),
  the extra tools (`sum_amounts`, `subtract_amounts`), the draft-form renderer
  (`src/draft_form.py`), an MCP server for the tax tools, and tests for all of them.
- Found two wrong 2025 bracket tops in `tax_math.py` (checked against IRS Rev. Proc. 2024-40
  with a web search) and fixed them with tests.
- Wired document redaction into the shared runner and added tests that traces hold no SSNs.
- Merged the latest `main` into my branch and adapted Computation to the real Intake names.
- Drafted `docs/provenance.md` and my report section.

**What I decided or checked myself**
- Chose to leave unresolved questions for teammates as TODO placeholders in
  `docs/provenance.md` instead of interrupting them, and approved each commit and push.
- [Add anything else you checked yourself, e.g. opening demo/sample_1040sr.html and clicking amounts.]
