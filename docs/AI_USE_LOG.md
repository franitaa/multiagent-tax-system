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
- Acting on Francesca's review: switching to the shared `is_fake_ssn()` and telling
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

## Person 5 (Computation, provenance, security)
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
- Still to do myself before submission: open `demo/sample_1040sr.html` in a browser, click
  amounts, and record what I saw here.

## Person 5 (Sahana) — Tue Oct 27, 2026 (Computation and Security follow-up)
**Tool:** Claude Code (Claude Sonnet 5.5) in VS Code, on branches `p5/computation-no-arithmetic`
and `p5/redact-messages-at-boundary`.

**What the AI helped with**
- Audited `src/agents/computation.py` against the rule "Computation must not do arithmetic;
  every number comes from a deterministic MCP tool". It found Python addition, a `max(0, ...)`
  clamp, a head-count sum and bare `or 0` defaults, and moved all of them onto
  `sum_amounts` / `subtract_amounts`, with a provenance note for amounts not entered.
- Wrote `tests/test_computation_no_arithmetic.py`, an AST check that fails if arithmetic
  returns to the agent, and checked that it fails when `wages + interest` is put back.
- Closed a SEC-2 gap: real-looking SSNs could stay in `state["messages"]` when the graph
  was called without the chat page. The messages reducer now removes them
  (`remove_real_ssns`, `tests/test_boundary_redaction.py`).
- Ran the three scenarios (clean, interrupt, spouse-died) before and after the changes, and
  listed deliverables that are still missing from the repo.
- Committed and pushed the branches after I asked for pull requests.

**What I decided or checked myself**
- Asked whether the arithmetic rule was met, approved the fixes, and chose to submit pull
  requests rather than commit by hand.
- Review the diffs and pull request text before merging.

**How the AI's work was verified**
- Full pytest run before each commit (825, then 831 passing, 2 expected failures), and the
  scenario runs reached "DRAFT READY" with the two branches combined.

**Limits I am aware of**
- The AST test allows string and list joins with `+`; it checks the operators in one file,
  not every route a number could take.
- The redaction pattern removes any 9-digit number that is not 900-999, so a 9-digit
  number that is not an SSN would also be removed from a chat message.

## Matthew — Tue Oct 27, 2026 (Eligibility & Rules Agent)
**Tool:** ChatGPT (OpenAI), used for reviewing Python code, test design, and explanations while working on the multi-agent tax-system repository.

**What the AI helped with**
- Interpreted Assignment 7's Eligibility & Rules responsibilities: Form 1040-SR eligibility, filing-status validation, age/blindness boxes, supported tax scope, and escalation to volunteers.
- Reviewed the Rules code and the Intake-to-Rules field contract. Suggested reading the shared `facts` records (`taxpayer_birth_date`, `married_dec31`, `file_jointly`, `household_situation`, `taxpayer_blind`, and related fields) instead of relying on old stub names.
- Suggested explicit parsing of `"yes"`, `"no"`, and `"not_sure"`, and deriving filing status in Rules rather than expecting Intake to supply it.
- Explained the existing escalation conditions and how `handoff_request` differs from a real pending `escalation`.

**What I decided or checked myself**
- Used the team's `docs/answer-names.md` as the reference for Intake fact names and value shapes.
- Reviewed the suggestions against my Rules responsibility and discussed integration questions with the Intake and orchestration teammates.

**How the AI's work was verified**
- Reviewed the Python code and team contracts; later tested the updated behavior in my local repository using pytest.

**Limits I am aware of**
- A Rules unit test does not establish that the orchestrator honors a human handoff or that a draft return is completed correctly.

## Matthew — Wed Oct 28, 2026 (Rules citations and human-review behavior)
**Tool:** ChatGPT (OpenAI), used for code suggestions, test generation, debugging, documentation, and GitHub comment drafting.

**What the AI helped with**
- Suggested pairing every applied rule with a policy citation in `eligibility["rule_citations"]`, using numbered sections of `data/policy.md` and a helper function to avoid duplicate entries.
- Helped revise `tests/test_rules_policy_citations.py`, investigate failures from outdated field expectations, and add the missing Form 1099-R Box 2b citation (`policy.md §3.2`).
- Helped debug the `"not_sure"` blindness case: keep confirmed age boxes, do not count unconfirmed blindness, and refer unresolved answers to Human Review rather than returning to Intake.
- Reviewed teammate feedback explaining why a handoff request by itself can be ignored by the router. Suggested a real pending escalation and helped draft a response for PR #21.
- Drafted updates to `docs/handoff-contract.md` describing Rules' output and the citation structure.

**What I decided or checked myself**
- Chose the paired `rule_citations` format and asked that the old fields not be retained in the contract description.
- Reviewed teammate comments and agreed that uncertain blindness should be resolved by a volunteer without losing the known age box.
- Ran the policy-citation tests in my own project and shared the failing output to identify the missing Box 2b citation; I subsequently confirmed that those tests passed.

**How the AI's work was verified**
- The policy-citation suite passed locally after the missing 1099-R citation was added (17 tests in the suite discussed).
- The reviewer independently found that a handoff-only blindness response did not pause the full workflow, so this integration behavior was not considered verified.

**Limits I am aware of**
- AI-generated tests and documentation must be checked against the actual branch, the supplied `policy.md`, and the orchestrator's state contract.

## Matthew — Thu Oct 29, 2026 (ANSWER_UNCERTAIN, filing status, and regression tests)
**Tool:** ChatGPT (OpenAI), used for code review, Python test-suite drafting, and interpreting pytest failures.

**What the AI helped with**
- Reviewed `rules(6).py` and `rules(7).py` and suggested using the agreed `ANSWER_UNCERTAIN` condition for relevant `"not_sure"` answers (`married_dec31`, `file_jointly`, `household_situation`, `taxpayer_blind`, and `spouse_blind`).
- Suggested preserving confirmed age/blindness boxes, raising `escalation["pending"] = True`, and rereading human-corrected facts on a resumed Rules run.
- Helped maintain `HUMAN_GATE_NAMES` for volunteer filing-status inputs while outputting canonical long names (for example, `married_filing_jointly`) through `eligibility["filing_status"]` for Computation.
- Generated and refined Rules regression tests covering all five filing statuses, uncertainty escalation, volunteer corrections, tax scope, citations, Social Security rules, and Forms 1099-R and 1099-NEC.
- Helped interpret errors caused by a missing `ANSWER_UNCERTAIN` constant in `src/state.py`, a missing local `data/policy.md`, and an obsolete strict `xfail` marker for the now-passing 1099-NEC screening test.

**What I decided or checked myself**
- Chose to keep short status codes inside Rules calculations but return the long-form names expected by Computation.
- Worked with the team's proposed `ANSWER_UNCERTAIN` contract rather than reusing `SOURCE_CONFLICT` for uncertain answers.
- Added or tested a check for extracted 1099-NEC documents that Intake might not flag, and reviewed the test outcomes in my local PowerShell environment.

**How the AI's work was verified**
- A local `test_rules.py` run reported 107 passing tests and one `XPASS(strict)` after the 1099-NEC behavior was implemented. The strict XPASS indicated that the obsolete expected-failure marker needed to be removed; it was not evidence of a broken Rules calculation.
- Separate AI-provided validation runs used isolated test environments; they do not substitute for running the full project and end-to-end human-review scenarios.

**Limits I am aware of**
- Real pause/resume behavior, volunteer resolution storage, and final draft propagation require integration tests with the actual orchestrator, human gate, and Computation agent.
- I still need to verify the final branch's full test run and record any remaining integration issues before submission; AI-generated files are not automatically committed or pushed to GitHub.

## Matthew — Fri Oct 30, 2026 (contract confirmation and AI log, demo day)
**Tool:** Claude (Claude Opus 5.5) in the Claude in Chrome side panel. It read the repository
through my logged-in GitHub browser session and edited files in the GitHub web editor.

**What the AI helped with**
- Explained my P1/P2 tasks in issue #41, and suggested how to raise `SOURCE_CONFLICT` in Rules
  (compare the `has_*` answers with uploaded document kinds); not implemented yet.
- Reviewed my draft of `docs/intake-rules-contract.md` against `rules.py`, `answer-names.md` and
  `src/orchestration/context.py`. It found missing facts in the mapping (`spouse_can_be_claimed`,
  `spouse_death_year`, the `has_*` answers) and that the `has_*` answers are not in `RULES_FACTS`,
  so a `SOURCE_CONFLICT` check must add them there.
- Rewrote sections 1, 2, 3 and 5 of the contract to match the current code, and recorded the
  agreed `not_sure` decision.
- Looked up the dates of my ChatGPT sessions (only dates are shown, not times) to help me
  write the entries above, and committed both files to a branch for a pull request.

**What I decided or checked myself**
- Agreed with Supriya that a `not_sure` screening answer is escalated, not re-asked.
- Confirmed the mapping for Rules; Supriya confirms the Intake side on the pull request.
- Chose to commit through a branch and pull request rather than to `main`, and approved each commit.

**How the AI's work was verified**
- The contract statements were checked against `rules.py` and `context.py` on `main`, and the
  1099-NEC test name against `tests/test_rules.py`. Claude could not run the tests; I run
  `pytest` locally before merging.

**Limits I am aware of**
- Documentation only this session: no code changed, so `SOURCE_CONFLICT` is still to do.
