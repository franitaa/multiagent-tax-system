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

## Supriya Patil — Tue Oct 27, 2026
**Tool:** Claude Code (Claude Opus 5.5) in VS Code, on my branch `feature/intake-review-fixes`
(PR #16, merged Oct 29). Review work was done in temporary copies of the repo, never on
teammates' branches.

**What the AI helped with**
- *Acting on Francesca's review of my guardrails.* She pointed out that the pressure check
  (escalation condition 6, `EXPLOITATION_SIGNS`) used exact phrases, so realistic wording
  was missed: "he is making me do this", "my son keeps my refund", "she told me not to tell
  anyone". The AI rewrote the check in `src/agents/intake_agent.py` as patterns (who
  *keeps / takes / controls* *my* refund or money; being *forced*; being told *not to tell
  anyone* or *what to say*; fear of a named person; "put me in a home"; someone changing the
  person's bank details or holding their passwords or ID; and scams aimed at older people
  such as "pay the IRS with gift cards" and "wire money").
- *Growing the adversarial test set* (`tests/test_guardrails.py`, card GRD-3) from 20 to
  53 messages that must raise the right alarm, and from 15 to 38 innocent messages that must
  not ("my daughter is making me lunch", "the bank keeps my statements", "my wife is scared
  of dogs", "I have no choice but to wear glasses"). Each alarm is also checked to carry
  only a generic reason, never the person's own words.
- *A "3 tries" rule:* if Intake cannot read an answer three times in a row, it says "Let's
  not worry about this one", notes the question for a volunteer and moves on, so an older
  person is never stuck in a loop. Two tests check it, including that the count starts
  again for each question.
- *Dark mode:* Shruti saw dark buttons on a white page on her Mac. The AI added
  `.streamlit/config.toml` (always the light theme) and a CSS safety net in the chat page,
  plus a test that the light theme is set.
- *Team review before the 3 pm meeting:* it merged teammates' branches with main in a
  temporary copy, ran all tests, and listed what was blocking whom; it also drafted my
  meeting notes in plain words.

**What I decided or checked myself**
- Asked for more pressure phrasings after reading the first list, and approved the calm,
  non-accusing reply ("Thank you for telling me. Before we go on, I'm going to ask a
  volunteer to look at this with you.").
- Asked whether a new PR was needed; kept the work in PR #16 once I understood that new
  commits on the same branch join the open PR.
- Raised on Matthew's Rules PR (#14, tagging Francesca) that a "not sure" answer about
  blindness gave zero boxes and never reached a volunteer, and suggested counting the age
  box anyway. This later became the `ANSWER_UNCERTAIN` alarm.
- Asked to understand, in plain words, how the Intake agent works and whether it meets the
  brief, before the meeting.

**How the AI's work was verified**
- The whole team suite before each commit (549 passing at the end).
- The innocent-message list exists to catch false alarms from the broader patterns; every
  new pattern had to pass it.

**Where the AI got it wrong (and how it was caught)**
- Its first pressure check missed realistic phrasings; this was found by a teammate's
  review, not by the AI, which is why the adversarial list was extended.

## Supriya Patil — Wed Oct 28, 2026
**Tool:** Claude Code (Claude Opus 5.5) in VS Code. All review work in temporary copies
(git worktrees) in a scratch folder, so my branch and teammates' branches were not touched.

**What the AI helped with**
- *Reviewing the team's open pull requests* (#15 JiWon, #17–#20 Sahana, #21–#22 Matthew):
  it combined each one with main and with my PR #16 in a temporary copy, set up a separate
  Python 3.11 environment for the PRs that needed it, and ran every test. Findings:
  - main was broken (19 failing tests) because Matthew's new `tests/test_rules.py` had been
    pushed to main without the matching `rules.py`, which was still in PR #21;
  - "not sure" about blindness was sent as a *handoff request* to a human, which the
    orchestrator ignores, so no volunteer was ever asked (checked by running Rules and
    reading the router);
  - Sahana's PRs had added the draft form to my chat page, and the combined code passed
    (828 tests); a full taxpayer conversation reached "finished" with a draft;
  - JiWon's PR #15 and Sahana's PRs clashed in four files, including my test file.
- *Which agents use a language model:* it searched every branch; only Extraction (JiWon)
  uses one, to read W-2 images. It then checked the assignment text: no rule requires a
  model in every agent (only §4.5 mentions "model-calling agents").
- *A question to the professor:* drafted, then shortened, an email asking whether
  rule-based agents are acceptable if each choice is explained.
- *Class discussion notes:* my role line for the group spreadsheet, answers to the
  professor's eight questions from our project, and a one-page ethics and guardrails brief,
  as an editable Word file.
- *API keys:* checked how `.env` and `.env.example` are handled (the real `.env` is
  git-ignored and kept out of the Docker image) and what the brief asks (§5.1 lists
  `.env.example`; graders need run instructions).

**What I decided or checked myself**
- Sent the review messages to Matthew, Sahana and JiWon after reading them, and decided to
  raise the real-numbers question at the 3 pm meeting rather than earlier.
- Asked for the professor email to be generic (on behalf of the team) and concise.
- Chose the class question I would lead ("general rules, or letting the chips fall?"),
  after the group split the question with Person 1; asked for a simple everyday example
  to explain that we had built similar things under different names.

**How the AI's work was verified**
- Every review claim was backed by a test run or by reading the code it named; claims it
  could not check (GitHub comments in our private repo) were stated as such.

**Where the AI got it wrong (and how it was caught)**
- One of its search commands was garbled by the Windows Git shell and returned errors; it
  re-ran it correctly before drawing any conclusion.

## Supriya Patil — Thu Oct 29, 2026
**Tool:** Claude Code (Claude Opus 5.5) in VS Code, on my branches `feature/chat-draft-form`
(PR #28, merged), `feature/saved-sessions` (PR #34), `feature/volunteer-dashboard` (draft
PR #35) and `docs/ai-log-supriya-oct27-29` (this log). Headless Chrome was used to take
screenshots of the pages.

**What the AI helped with**
- *PR #28 (draft form on the finished chat page):* added the change Sahana had prepared,
  so the two tests waiting on me in #24 passed. After #24 was merged, it checked GitHub's
  own trial merge to confirm that moving the PR's base to main would change only my two
  files (GitHub's page still showed an old "54 commits" count), and guided me through the
  merge.
- *Python 3.11:* the team moved to 3.11, so it rebuilt my local environment, keeping the old
  one under a descriptive backup name and checking that it can never be uploaded.
- *Saved sessions (PR #34):* the chat page now uses JiWon's SQLite checkpointer (the team's
  shared file, which Sahana's retention tool also cleans), so a case ID still works after
  the app restarts. A test answers two questions, "restarts" the app and continues.
- *Chat page changes I asked for (PR #34):* each question shown only once (no repeated chat
  history; screen readers no longer read it twice); month names only; a typing box labelled
  "MM-DD-YYYY, for example: 03-04-1950" that also accepts 03/04/1950 and 03041950, read
  month-first because the label says so, and still read back to the person ("Just to check:
  you were born on March 4, 1950?"). It also updated my report section to match.
- *Volunteer dashboard (draft PR #35):* every case with its status in words; what each case
  needs, including quiet requests that do not pause the chat ("asked to talk to a
  volunteer", "not sure" answers); summary card, donut charts (with the numbers also as
  text for screen readers), filter buttons and search; one case's alarm, the taxpayer's own
  words, answers (SSNs masked), draft form and audit-log history with its tamper check.
  Resolving goes through Francesca's human gate unchanged (only the allowed choices, a
  note, the volunteer's name, written to Sahana's audit log; opening a case is recorded as
  "viewed"). A "Check again" button on the taxpayer's waiting screen.
- *One start page* (`src/ui/silverfile_home.py`): "I'm a taxpayer" or "I'm a Kushim
  volunteer" in one app, so both pages always share the saved sessions (two Docker
  containers would not). README updated with the command and an end-to-end walk-through.
- *Visual design:* a common look for all pages, then screenshots in a real browser (normal
  width, small screens, and a computer in dark mode). Icons were switched from emoji to the
  icon font shipped with the app, so they look the same on Windows, Mac and phones, and
  Streamlit's "Deploy" developer button was hidden.
- *Checking every "call a human" point* across all six agents: all go through one human
  gate, so all reach the dashboard; but no agent yet raises "an answer does not match a
  document" (one of the six required conditions), which I reported to the team.
- *Reviewing JiWon's API-key PR (#32):* the README still told graders to type the key in a
  box that had been removed, and Docker passes the key in a way the new code no longer read.

**What I decided or checked myself**
- Answered the team's question in #24: the taxpayer may see and download the draft,
  matching Sahana's version. Merged PR #28 myself.
- Found these problems in my own testing and chose the fixes: the question shown twice
  (chose "one question per screen" after seeing it live); "2 - February" looking like
  2 February; no example in the date box (chose MM-DD-YYYY with dashes); a white button
  with invisible text; pages that looked too plain; the dashboard design (I supplied a
  reference image); that the look must be the same on Apple computers.
- Tested saved sessions myself: closed the page and had the app restarted, then continued
  with my case ID.
- Checked that nobody had started a dashboard, told the group before building it, and
  asked for it as a draft PR so teammates could give feedback before merging.
- Decided the next steps: a volunteer passcode so taxpayers cannot open the dashboard; a
  limited AI helper only for answers the rules cannot read (always read back to the person,
  rules stay in charge); better replies to "why does it matter?"; and catching "I was, but
  he died" as a spouse who died during the year.

**How the AI's work was verified**
- The full team suite before every commit (1,018 passing at the end; the only 3 failures
  are Review tests that Shruti's PR #30 fixes, checked by combining all open PRs: 1,099
  passing, 0 failing).
- New tests for each change: logic tests for the dashboard, and page tests that click
  through as a volunteer (open a case, resolve it, check the audit log). The "question shown
  once" test was checked to fail on the old page, so it really tests the change.
- Screenshots in a real browser, because tests cannot see colours or layout.

**Where the AI got it wrong (and how it was caught)**
- Saved sessions first failed with "Cannot operate on a closed database" (the saver closed
  itself too early); caught by the page tests and fixed in my code, without changing JiWon's.
- Both pages used the same memory slot (`case_id`), so opening a case in the dashboard
  would have switched the taxpayer's session; caught while combining the pages, now covered
  by a test.
- Its new blue button style was weaker than an existing white-button rule, so the text was
  invisible; I spotted it in the browser. The same bug on the dashboard's Refresh button
  was then found by the screenshots.
- It twice wrote a test line that checked nothing or clicked an arbitrary button; it
  noticed and rewrote them before committing.
- It credited a teammate in a commit message with a made-up email address; it corrected
  the message before pushing.

**Limits I am aware of**
- The dashboard has no login yet (a passcode is next on my list).
- I could not test on a real Mac; dark mode, fonts and icons are now controlled by the app.

## Person 5 (Sahana) — ChatGPT, Oct 22 to Oct 25, 2026 (before switching to Claude Code)
**Tool:** OpenAI ChatGPT.

**What the AI helped with**
- Helped me understand the project and the work I needed to do as Person 5 (Computation, provenance and security).
- Started the first versions of `provenance.py`, `tax_math.py`, the Computation agent (`src/agents/computation.py`) and the tests for them. Claude Code continued and changed them afterwards.

**What I decided or checked myself**
- After Oct 25 I switched to Claude Code, which made the changes described in the entries above.
## Person 5 (Sahana) — Mon Oct 26, 2026 (Computation, provenance, security)
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

## Person 5 (Sahana) — Wed Oct 28, 2026 (security and Computation integration)
**Tool:** Claude Code (Claude Sonnet 5.5) in the terminal, on branch `p5/oct27-followups`
and the branches it fed into.

**What the AI helped with**
- Moved the tax-tool calls to MCP (a stdio client, on by default, with no silent fallback) and added
  `mcp==2.3.0` to `requirements.txt`.
- Added the prompt-injection defences, the hash-chained audit log (`src/audit.py`) and case retention
  (`src/retention.py`, `scripts/purge_cases.py`).
- Made Computation act on Review send-backs, and wrote the draft form from a completed run.
- Redacted escalation reasons and volunteer notes before they reach state, and removed real-looking
  SSNs from chat messages at the state boundary (SEC-2).
- Corrected two 2025 bracket tops in `tax_math.py` against Rev. Proc. 2024-40, with tests.

**What I decided or checked myself**
- Reported to the team that the SEC-2 commit messages described runner and state changes that were not in the committed diff, rather than leaving the mismatch unmentioned.

**How the AI's work was verified**
- The full pytest suite before each commit. The remaining failures were listed in the P5 README
  rather than hidden.

**Limits I am aware of**
- The audit chain does not detect deletion of the last lines, and the volunteer name is whatever the
  caller supplies (there is no login yet).

## Person 5 (Sahana) — Thu Oct 29, 2026 (review fixes, unread income forms, merge)
**Tool:** Claude Code (Claude Sonnet 5.5) in the terminal, on branches `p5/clean`,
`p5/in-scope-income-warning` and a test-fix branch for PR #31.

**What the AI helped with**
- Fixed the two send-back tests on PR #30's branch by giving them an Extraction stand-in that returns
  text amounts (`tests/helpers.py`), and opened PR #31 with Shruti as reviewer.
- Investigated an MCP test failure. The cause was the stub Review on `p5/clean`, which PR #30 replaces.
- Added the unread in-scope income safeguard (issue #27, PR #33): Computation and the draft form warn
  when an SSA-1099, 1099-INT or 1099-DIV has no amount, and never invent one.
- Moved the shared income-form code to `src/income_forms.py` after Francesca's review, so the draft form
  does not import an agent, and added a test that checks this.
- Merged `main` into `p5/clean` after PR #33 and ran the full suite.

**What I decided or checked myself**
- Chose to keep my three local test edits in a stash, since `main` already had identical content.
- Chose `src/income_forms.py` over `src/tax_tools.py`, because the tax-tool list says it imports only
  `tax_math`.
- Posted the replies on PR #33 and PR #35 myself, and corrected the #35 wording after PR #33 merged.

**How the AI's work was verified**
- Full suite on the merged branch: 1100 passed, 3 xfailed.

**Limits I am aware of**
- Issue #27 is only partly fixed: the draft warns, but the amounts still need Intake and Extraction work.

## Person 5 (Sahana) — Fri Oct 30, 2026 (typed income amounts, PR #40 review, retention)
**Tool:** Claude Code (Claude Sonnet 5.5; part of the session ran on Claude Haiku 5.5 before the model was switched) in VS Code, on branches `p5/typed-income-amounts`,
`p5/retention-uploads` and `p5/issue-41-typed-amounts`.

**What the AI helped with**
- Issue #41 P1 (issue #27, step 2): Computation reads amounts the taxpayer types for SSA-1099, 1099-INT
  and 1099-DIV as direct-input records, and a form with a typed amount counts as read. Merged in PR #46.
- Read PR #40 and ran its tests on a temporary copy of `main` with the PR merged. Posted a comment
  review on #40. Nine page tests failed on my machine because my Streamlit (1.50.0) was older than
  the pinned 1.66.1; they pass with the pinned version, so they were not a problem in `main`.
- Retention: the purge now removes the uploads (`runtime/uploads/<sha>.png`) that a case was read
  from, and the stale-upload sweep skips uploads a saved case still points at. Two tests added.
- Updated the retention wording in `docs/security.md` and the P5 README, with a scheduling example.

**What I decided or checked myself**
- The fact names in `docs/answer-names.md` are proposed, not agreed with Intake. Supriya confirmed them in her review of PR #46.
- The Windows Task Scheduler example has not been tested on this machine.

**How the AI's work was verified**
- Typed-amount change: full suite 1109 passed, 3 xfailed before the commit.
- Retention: `tests/test_retention.py` 18 passed.

**Limits I am aware of**
- One typed amount marks its whole form as read, so a missing withholding on that form is not flagged.
- The scheduled purge only runs if someone sets up the schedule.

## Person 5 (Sahana) — Fri Oct 30, 2026 (later: review fixes on PR #44 and #46, reviews, README, assignment check)
**Tool:** Claude Code (Claude Sonnet 5.5) in VS Code, on branches `p5/retention-uploads` and
`p5/issue-41-typed-amounts`.

**What the AI helped with**
- PR #44: added the test Francesca asked for (an `image_ref` such as `../victim` removes nothing and does not fail
  the purge) and checked it fails when the 64-hex check is removed. Replied that the nine failing page tests were my
  out-of-date Streamlit, not a problem in `main`. PR #44 is merged.
- PR #46: Supriya found that typed amounts failed Review in a real run (three rounds, then
  `REVIEW_BOUND_EXCEEDED`), which my tests had missed because they never called Review. Shruti pointed at the cause,
  the source label `User-provided value` in `provenance.py`. The AI changed it to `direct user input`, and made a read
  document take priority over a typed amount for the same form, so nothing is counted twice. It added tests that run
  real Computation then real Review. Francesca's PR #51 fixed the same label, and Shruti's PR #54 replaced my
  `review.py` change with hers, so only the Computation, provenance and test changes are mine. PR #46 is merged.
- Read and commented on PRs from teammates: #52 and #57 (policy text; approved #57), #55 (ran the merged result
  locally: 1324 passed), #56 (confirmed the two-line test change; found that a volunteer-corrected W-2 amount still
  says "Document Extraction" in its source) and #60 (Docker and CI; no changes needed).
- Compared the assignment brief with `main` and opened issue #59 listing the document gaps (AI disclosure,
  roles table, README, small items).
- Wrote a short Computation paragraph for the report and updated my README section (`docs/README-p5-computation-security.md`).

**What I decided or checked myself**
- Chose to prefer the document over the typed amount instead of raising a volunteer escalation, to keep the change small.
- Decided what to post, approve and merge-order advice myself; told the AI not to push the last merge into PR #46 once it had merged.
- Did not change teammates' files; raised the points on their pull requests instead.

**How the AI's work was verified**
- PR #46 branch merged with `main`: 1254 passed, 3 xfailed. Scratch merges of #55 and #56 with `main` ran cleanly.

**Limits I am aware of**
- Intake does not yet ask for the SSA-1099, 1099-INT and 1099-DIV amounts, so typed amounts reach Computation only once it does.
- The README section is not yet in a pull request.

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

## Ji Won Park — October 26, 2026 (Document Extraction & Agent Memory)

**Tool:** ChatGPT (OpenAI), used for setup troubleshooting, explanations, and testing guidance.

**What the AI helped with**

- Explained how to run the project on Windows using VS Code and a Python virtual environment.
- Helped troubleshoot dependencies and explained the Tesseract requirement for image extraction.
- Explained case IDs, checkpointing, and how to test saved answers and resumed sessions.

**What I decided or checked myself**

- Ran the checkpoint pause/resume and intake-answer save/resume examples.
- Checked that the case ID, summary, and next-question position were retained.

**How the AI's work was verified**

- Checked the command outputs and ran the unit suite: 60 tests were reported, with 12 skipped.

**Limits I am aware of**

- The skipped image and integration tests did not verify actual W-2 image extraction.

## Ji Won Park — October 27, 2026 (Document Extraction & Agent Memory)

**Tool:** ChatGPT (OpenAI), used for reviewing test failures and explaining shared graph state.

**What the AI helped with**

- Reviewed a failing extraction integration test and its saved state.
- Explained the difference between an empty `computed` dictionary and a missing `computed` field.

**What I decided or checked myself**

- Ran the tests and inspected the failure output.
- Checked that the case was awaiting human extraction review and contained no calculated amounts.

**How the AI's work was verified**

- The test output showed 242 passed tests, one failure, and five passed subtests.
- The failure concerned an assertion about the presence of the `computed` key.

**Limits I am aware of**

- Diagnosing this assertion did not verify the complete extraction, review, and restart workflow.

## Ji Won Park — October 29, 2026 (Document Extraction & Agent Memory)

**Tool:** ChatGPT (OpenAI), used for Python changes, documentation, debugging, and Git guidance.

**What the AI helped with**

- Suggested changes to read API keys from `.env` and remove the sidebar key input.
- Helped update configuration instructions for OpenAI and Anthropic.
- Drafted an initial connection between chat sessions and W-2 storage.
- Helped diagnose indentation and UI-test failures.

**What I decided or checked myself**

- Applied the changes in VS Code, ran tests, and committed changes through my working branch.
- Kept actual API keys out of the committed configuration template.

**How the AI's work was verified**

- After corrections, the local suite reported 760 passed tests and five passed subtests.
- Submitted the changes for teammate review.

**Limits I am aware of**

- Local tests did not prove compatibility with newer team changes.
- The initial integration changed shared chat and routing files too broadly. Teammate feedback led to separating those changes from the API-key PR.

## Ji Won Park — October 30, 2026 (Document Extraction & Agent Memory)

**Tool:** ChatGPT (OpenAI), used for code review, test design, integration explanations, and documentation.

**What the AI helped with**

- Helped narrow PR #32 to API-key handling and related setup instructions.
- Drafted the P3 shared-service adapter and tests for using the chat's existing case ID and checkpointer.
- Explained how to preserve intake answers and existing documents when adding W-2 uploads.
- Helped prepare integration instructions and the Extraction and memory report sections.

**What I decided or checked myself**

- Followed teammate feedback to separate shared integration work from the API-key PR.
- Tested a synthetic W-2 through the standalone workbench using my OpenAI key.
- Ran the adapter and full test suites before pushing changes.
- Confirmed that extraction would remain W-2 only and coordinated chat UI integration with the Intake owner.

**How the AI's work was verified**

- The API-key branch reported 1,100 passed tests, three expected failures, and five passed subtests after incorporating main.
- The adapter tests reported nine passed tests and five passed subtests, including preservation of saved answers and documents after reopening the database.
- The full suite after adding the adapter reported 1,145 passed tests, three expected failures, and ten passed subtests.
- Teammate review identified further integration requirements before PR #39 was merged.

**Limits I am aware of**

- My successful OpenAI test used the standalone workbench, not the complete chat upload flow. I had not personally verified a live Anthropic call.
- Adapter tests do not prove that the chat UI, routing, and dashboard work together correctly.
- Vision results require human verification. Model-assisted identifier screening does not guarantee that real identifiers are blocked before transmission.

## Francesca Rondinella (Person 1, orchestration) — Sat Oct 25, 2026 (graph, runner, human gate, context strategy)
**Tool:** Claude Code (Claude Sonnet 5.5) in VS Code, on branches `orchestration-setup` and `orchestration-phase3`.

**What the AI generated**
- Wrote the first versions of `src/state.py`, `src/graph.py`, the runner with JSONL tracing, the stub agents and the
  agent contract (`docs/handoff-contract.md`), from the rules in `CLAUDE.md`.
- Escalation routing and the human gate (`interrupt` and `Command(resume=...)`), including stop-only conditions,
  a required note for "continue", and queued flags.
- Parallel extraction with order-independent merging, the bounded review loop and the loop guard.
- The context strategy: narrowed views per agent, the Intake chat window, a rolling summary, the
  `--no-context-strategy` flag, `scripts/` measurement and `docs/decisions/001-context-strategy.md`.
- Commit messages; git commands after I approved each step.

**What I decided or checked myself**
- The architecture (hub-and-spoke; the Orchestrator never extracts, computes or talks to the user) and the six-agent rule.
- Which conditions are continuable and which are stop-only.
- That other people's agents stay stubs and I do not write their tax or intake logic.

**How the AI's work was verified**
- `pytest` before each commit, as `CLAUDE.md` requires, and the demo cases run through the real graph.

**Limits I am aware of**
- The first context numbers in `docs/metrics.md` come from stub agents, so they show the mechanism, not real costs.

## Francesca Rondinella (Person 1, orchestration) — Mon Oct 26, 2026 (Intake and Rules integration findings)
**Tool:** Claude Code (Claude Sonnet 5.5) in VS Code.

**What the AI generated**
- Reviewed the Intake and Rules branches against the contract and wrote end-to-end and contract tests with the
  real Intake and the real Rules.
- Found that Rules and Intake used different fact names and value shapes (for example `bool("no")` is `True`),
  and documented it in `docs/intake-rules-contract.md`.
- Added `ELIGIBILITY_UNDECIDED`: a case no longer ends "complete" without a filing status and an eligibility verdict.
- Updated `docs/STATUS.md`, the README run instructions and the graph diagram.

**What I decided or checked myself**
- That the mapping stays marked unconfirmed until its owners (Matthew and Supriya) confirm it.
- That the missing escalation for out-of-scope screening answers is tracked, not fixed by me.

**How the AI's work was verified**
- Tests run before each commit; the new tests were written to fail on the old behavior.

**Limits I am aware of**
- The contract was my reading of the code, not an agreement. It was confirmed only later (#49).

## Francesca Rondinella (Person 1, orchestration) — Wed Oct 28, 2026 (integration of the real agents)
**Tool:** Claude Code (Claude Sonnet 5.5) in VS Code.

**What the AI generated**
- Removed the expected-failure markers that Matthew's Rules now satisfied, and updated two of my own tests to the integrated behavior.
- `live_agents()` (one definition of the real agent set) and a narrower Rules view of facts.
- A tax-tool server that cannot start now ends the case as `halted_by_error` (no traceback, an audit entry).
- The filing-status vocabulary contract test; `.gitignore` for case data, audit logs and env files.

**What I decided or checked myself**
- That a failure to start the tools halts the case instead of falling back silently.
- That Rules sees only the facts it reads (recorded in a decision, enforced by a test).

**How the AI's work was verified**
- Full `pytest` run before each commit; metrics regenerated from the integrated graph.

**Limits I am aware of**
- Two status vocabularies still existed at the end of the day; a failing volunteer filing-status test said so.

## Francesca Rondinella (Person 1, orchestration) — Thu Oct 29, 2026 (ANSWER_UNCERTAIN, Python 3.11, telemetry spec)
**Tool:** Claude Code (Claude Sonnet 5.5) in VS Code, on branches `p1/phase5-integration`, `p1/status-reruns-rules`
and `p1/telemetry-dashboard`.

**What the AI generated**
- `ANSWER_UNCERTAIN` as a registered, continuable condition; after a volunteer's answer the gate clears `eligibility`
  so Rules decides again. The same fix for a volunteer's filing status (#29).
- Moved the project to Python 3.11 (CI, `requires-python`, the lock file, `mcp==2.3.0`).
- Extraction no longer waves through a document it cannot read; a known-gap test now points at issue #27.
- The docs pass (handoff contract, STATUS, Intake-to-Rules contract).
- The telemetry dashboard: its spec, the read-only module `src/telemetry.py` over `traces/` and the audit log, and the page.
- Reviewed teammates' pull requests (#30 and others): read the diff, ran the tests on a temporary copy with `main` merged.

**What I decided or checked myself**
- Telemetry is a bonus and not an agent: read-only, no change to the graph (decisions are in the spec).
- Python 3.11 only, so that CI and the team run the same version.

**How the AI's work was verified**
- Tests before each commit; each new test was checked to fail without its fix.

**Limits I am aware of**
- A first test for #29 passed without the fix (wrong scenario); it was rewritten to mirror the eval and then failed without the fix.

## Francesca Rondinella (Person 1, orchestration) — Fri Oct 30, 2026 (INCOME_NOT_READ, review round, team to-do list)
**Tool:** Claude Code (Claude Sonnet 5.5) in VS Code, on branches `p1/income-not-read`, `p1/verify-chat-extraction`,
`p1/shared-service-docs`, `p1/direct-input-label` and others; pull requests and comments through the `gh` CLI.

**What the AI generated**
- `INCOME_NOT_READ` (#40, issue #27): the orchestrator pauses a case once when an income form has no amount; a
  volunteer can continue only with a note, or stop. Router rule, human gate, dashboard words, docs and 27 tests.
- Fixes to JiWon's #39 after review, `scripts/verify_chat_extraction.py` (one real W-2 reading through the chat)
  and the integration notes in `src/p3/shared_service.py` (#42, #45).
- Found a bug on `main`: a typed estimated payment or adjustment failed Review because the helper labelled it
  "User-provided value" instead of "direct user input". One-line fix and three tests (#51).
- Reviewed #32, #35, #36, #38, #39, #43, #44, #46, #47, #48, #49, #55 and #56 by merging each with `main` in a
  temporary copy and running the tests; wrote the review comments.
- Put Supriya's request on #49 into code: a `not_sure` scope-screening answer raises `ANSWER_UNCERTAIN` so a volunteer
  confirms yes or no (`rules.py`, `human.py`, 34 new tests). Changes on #55 (the five `has_*` names in `RULES_FACTS`,
  `SOURCE_CONFLICT` re-runs Rules), pushed to the teammates' branches with their agreement.
- Resolved merge conflicts, drafted the team to-do list (issue #41), the merge order and the upload-flow proposal.

**What I decided or checked myself**
- Approved every comment, pull request and push before it was posted; asked for tags instead of names, and for the
  to-do list in Markdown to edit on GitHub.
- Chose the merge order, which review changes to accept, and that the router raises `INCOME_NOT_READ` instead of waiting on Review.
- Decided with Supriya and JiWon that the chat asks for the W-2 photo right after "yes", not at the last answer.

**How the AI's work was verified**
- Full `pytest` before each commit (1,304 passed, 1 expected failure on the last run) and the evals (15 of 15 pass, none pending).
- New tests were broken on purpose six ways for #40, and the #51 tests fail without the fix.

**Limits I am aware of**
- A first `sed` on macOS left conflict markers in a merge commit; it was rebuilt before pushing.
- I once told the team a merge conflict existed between #52 and #55; it did not, and the comment was corrected.
- The model stated a re-run of a failed CI job would help; a fresh push was needed. Stale "push" CI runs can show red while the "pull_request" run passes.
- Several features (typed SSA/INT/DIV amounts, `SOURCE_CONFLICT`) do not change a real run until Intake asks the amounts.

## Shruti Goel (Person 6) — Mon Oct 26, 2026 (Review/Audit agent, first CI)
**Tool:** Claude Code (Claude Opus 5.5) in VS Code, on branches `p6/review-agent` and `p6/ci`.

**What the AI helped with**
- Explained the repository and the brief's Review requirement (independently falsify the return).
- Wrote the Review/Audit agent (`src/agents/review.py`) and its tests, the tax-math tool registration
  and Review's access policy, and the line/box labels in `docs/handoff-contract.md`.
- Wrote the first GitHub Actions workflow (#12).

**What I decided or checked myself**
- Not to change Sahana's Computation stub while Review was being built: Review's own tests got their
  own consistent Computation instead, and the stub was left failing until her code landed.
- Asked for the line and box labels to be written into the existing team contract, not a new file.

**How the AI's work was verified**
- The full test suite before every commit; Review's tests against a correct reference return built
  with `tax_math`.

## Shruti Goel (Person 6) — Tue Oct 27, 2026 (Review against the real Computation, Docker)
**Tool:** Claude Code (Claude Opus 5.5) in VS Code, on branches `p6/review-agent` and `p6/docker`.

**What the AI helped with**
- Checked Review against Sahana's real Computation and fixed what was too strict (blank lines, text
  amounts, the filing-status names, spouse boxes on a joint return only).
- The Docker image, `.dockerignore` and the README's Docker section (#13); CI actions moved to Node 24.

**What I decided or checked myself**
- Which data Review sees: only numeric facts plus Rules' decisions, agreed with Francesca.
- To build and run Docker locally before pushing (I installed Docker Desktop for it).

**How the AI's work was verified**
- Docker built and run on my laptop (the clean case, the tests inside the container, the chat page),
  then the same steps in CI's `docker` job.

## Shruti Goel (Person 6) — Wed Oct 28, 2026 (reviewing teammates' PRs)
**Tool:** Claude Code (Claude Opus 5.5) in VS Code; review work only, in temporary copies of the repository.

**What the AI helped with**
- Read teammates' PRs (#11, #15, #24, #25) for what they changed in other people's files, and drafted
  my comments and team messages.
- Wrote the prompt Sahana used to split her own changes out of #11 into a P5-only PR (#24).

**What I decided or checked myself**
- That each PR should contain only its owner's work; Sahana's could keep the two lines her tests
  needed (`access.py` tool registration, `mcp==2.3.0`), and everything else was asked of its owner.

**How the AI's work was verified**
- Where a comment quoted test results, the PR was merged with `main` in a scratch copy and the tests
  were run first.

## Shruti Goel (Person 6) — Thu Oct 29, 2026 (eval cases, the Review PR)
**Tool:** Claude Code (Claude Opus 5.5) in VS Code, on branches `p6/evals` and `p6/review-agent`.

**What the AI helped with**
- The end-to-end eval cases and runner, run in CI, and the first instructions for eval cases 1 and 2
  (#26). CI moved to Python 3.11 only.
- Prepared the Review PR (#30) on a test copy of `main` + #24, and worked out which failing tests were
  whose.

**What I decided or checked myself**
- Checked the eval cases against the assignment's §5.2 and asked for the demo instructions.
- Questioned the AI's first Review graph test for the 1099-NEC case, which made Rules miss the document
  on purpose; it was replaced by a test of an out-of-scope line that only Review can see.
- Changed Francesca's eligibility-invariant test only with her permission.

**How the AI's work was verified**
- The evals against teammates' PRs in scratch merges (they found the filing-status name mismatch and
  Rules not running again after a volunteer's decision, both fixed by their owners).

## Shruti Goel (Person 6) — Fri Oct 30, 2026 (Docker volumes, evals, typed amounts, citations, demo)
**Tool:** Claude Code (Claude Opus 5.5) in VS Code, on branches `p6/docker-volumes`, `p6/evals-real-intake`, `p6/review-into-46`,
`p6/compose-drop-w2-page`, `p6/review-citations`, `p6/demo-click-through`, `p6/line-25c`,
`p6/dual-status-docs`, `p6/intake-form-amounts` and `p6/ai-log`.

**What the AI helped with**
- The #41 Docker run-through and its fixes (#47); the real-Intake eval cases (#48).
- Found that typed-in amounts failed Review while checking #46, and wrote the Review fix, merged into
  #46 through #54.
- Tested #52, #55 and #56 with the evals in scratch merges; found that #55's red check was GitHub
  testing against an old `main`.
- Took the old W-2 workbench out of Docker Compose and added CI checks for the chat W-2 flow and for
  purging a case's photo (#60).
- Review's check of Rules' policy citations against `docs/policy.md`, with a guard test (#65).
- Rewrote `demo/eval_case_1.md` and `eval_case_2.md` as click-by-click steps in the real app (#66).
- Resolved this log's merge conflict with #64; checked `main` against the assignment's deliverables
  list; drafted my report section (kept outside the repository, as the team decided).
- Line 25c on the draft, a $0 tool-made line with its reason (#68), plus a draft-form test for it after
  Sahana's review.
- The dual-status alien wording in `docs/provenance.md` and `docs/policy.md` (#69).
- Intake asks the SSA-1099, 1099-INT and 1099-DIV box amounts right after "yes" (#70, #27 step 2).
  Testing it found that "not sure" for a form's main amount plus a typed 0 for another box counted the
  form as read and dropped its income without a volunteer pause; the other boxes are now asked only
  once the main amount is a number.
- A fresh-clone run as a grader would do it, and the one real-AI check (`verify_chat_extraction`).

**What I decided or checked myself**
- Merged `main` into #55's branch myself so its CI tested it with #52; closed my duplicate #58 once
  Matthew's #57 covered Sahana's review.
- To build the `rule_citations` check rather than list it as a limitation, and to add the retention
  (purge) check to #60 itself rather than as a follow-up.
- To take the old W-2 workbench out of Docker Compose once the chat and dashboard handled the photo,
  because it writes demo answers into any case ID it is given.
- To change teammates' files only with their OK: line 25c in Sahana's Computation after she agreed;
  #70 in Supriya's Intake for her to review and merge.
- Corrected the AI's first dual-status wording: it said "not sure" to the residency question (Q23) stops
  as out of scope, but running it showed `ANSWER_UNCERTAIN`, and its policy §3.3 citation was wrong
  (§3.3 is about blindness). After review, the rule is attributed to the assignment (Assignment 7 §3.2).
- Put my own Anthropic key in `.env` myself (never pasted into the chat) for the real-AI check.
- Approved every push and PR; nothing was pushed to `main` directly.

**How the AI's work was verified**
- Docker run locally for each change (build, every page, a case shared between pages, a restart), then
  the same steps in CI's `compose` job.
- New Review tests were run against the earlier Review to confirm they fail there.
- The demo steps were checked by running both journeys through the chat and dashboard code with
  Ji's offline reader.
- The real AI reader was checked once with my Anthropic key: `python -m scripts.verify_chat_extraction
  --provider anthropic` read boxes 1 and 2 of `w2_01.jpg` correctly and ALL CHECKS PASSED (one paid call).
  The OpenAI provider was not run.
- Fresh clone (`main` at #69): 1369 passed; evals 15/0/0; the CLI cases, the app locally and in Docker.
- On `main` at #64 (Oct 30): 1353 passed; evals 15 pass, 0 fail, 0 pending.

**Limits I am aware of**
- The evals use stand-ins for Intake's answers and Extraction's boxes in most cases. The full chat
  flow with a W-2 photo is checked in CI's `compose` job, but with Ji's offline reader, not the real AI.
- A box a volunteer corrects still shows "Document Extraction" as its source on the draft, so Review
  cannot tell a corrected amount from a read one (the audit log has the decision).
- In eval case 2 the deceased spouse's age is not asked, so only the taxpayer's 65+ box is counted.

## Shruti Goel (Person 6) — Sat Oct 31, 2026 (deliverables, final checks)
**Tool:** Claude Code (Claude Opus 5.5) in VS Code, on branches `p6/deliverables` and `p6/ai-log`.

**What the AI helped with**
- Checked `main` against the assignment's deliverables list again, with what was still missing.
- `run.py` (one entry point for the app, the checks and the demo cases), copies of the two demo W-2s in
  `demo/`, `docs/for-graders.md` with a "For graders" README section, and `docs/fresh-clone-test.md` (#74).
- Found that a copy of the repository cloned inside the project folder made every test run twice and
  `pytest` fail there; it was removed.
- Resolved this log's merge conflict with #61.

**What I decided or checked myself**
- Rendered `docs/graph.png` myself from `docs/graph.mmd`; the AI was not allowed to send the diagram to
  an online renderer.
- To serve the app from `run.py` on this computer only, like Docker Compose, because the volunteer
  dashboard and `/telemetry` have no login.
- To keep the rules corpus at `docs/policy.md` (the assignment's layout says `data/policy.md`, but "does
  not need to be exact"), since Review, the tests and the docs all use `docs/policy.md`.
- Asked Francesca and Supriya to review #74.

**How the AI's work was verified**
- `python run.py check` on `main` plus #74: 1376 passed; evals 15 pass, 0 fail, 0 pending.
- Every link in the two new docs points to an existing file; the README section was placed so it does
  not overlap #72's changes.
