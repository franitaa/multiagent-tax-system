# SilverFile (multiagent-tax-system)

[![CI](https://github.com/franitaa/multiagent-tax-system/actions/workflows/ci.yml/badge.svg)](https://github.com/franitaa/multiagent-tax-system/actions/workflows/ci.yml)

A multi-agent system, built in LangGraph (Python), that helps prepare a **draft** US Form 1040-SR (tax year 2025)
for seniors, and keeps a record of where every number came from. A Kushim volunteer checks the draft; nothing is
ever filed.

Five business rules are enforced in code, not only in prompts:
- **Never file anything.** The output is a draft plus an audit record for a human.
- **Never give tax advice.** A request for advice is noted for a volunteer and the case pauses.
- **Never state an unsourced dollar amount.** Every amount carries a provenance record; the runner rejects one without it.
- **Always route the escalation cases to a human** through a LangGraph interrupt ([Human in the loop](#human-in-the-loop)).
- **Handle only the in-scope return profile.** Anything else escalates. Only test SSNs (900–999) and fictional documents.

The assignment makes one more a business rule: **six distinct agents, none merged** ([The six agents](#the-six-agents)).

**Contents:** [Quick start](#quick-start) · [Team and focus areas](#team-and-focus-areas) ·
[How it works](#how-it-works) · [The six agents](#the-six-agents) · [Human in the loop](#human-in-the-loop) ·
[Provenance, security and privacy](#provenance-security-and-privacy) · [Memory and context](#memory-and-context) ·
[Running it in more detail](#running-it-in-more-detail) · [Tests, evals and CI](#tests-evals-and-ci) ·
[Layout](#layout) · [Documents](#documents) · [Known limitations](#known-limitations) · [Contributing](#contributing)

## Quick start
**You need:** Python 3.11 or newer, or Docker. An OpenAI or Anthropic API key is optional: it is only used to read
W-2 photos. Full steps for a grader: [docs/for-graders.md](docs/for-graders.md).

```
cp .env.example .env              # optional: add an OpenAI or Anthropic key to read W-2 photos
docker compose up --build         # the app at http://localhost:8501 (cases kept between runs)
```

Or without Docker, in a virtual environment:

```
python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python run.py           # the app at http://localhost:8501
.venv/bin/python run.py check     # all tests, then the eval cases
.venv/bin/python run.py demo      # a clean case in the terminal, no key needed
```

The start page offers **I'm a taxpayer** (the chat) and **I'm a Kushim volunteer** (the dashboard). The two demo
cases, click by click: [demo/eval_case_1.md](demo/eval_case_1.md) (a clean run) and
[demo/eval_case_2.md](demo/eval_case_2.md) (a human-in-the-loop event, resolved). Without a key, the W-2 step says a
volunteer will help and the photo is not read.

## Team and focus areas
Each person owned one agent and one focus area of the assignment.

| Focus area | Person | Agent | What they built |
|---|---|---|---|
| Task division and management | Francesca Rondinella | Orchestrator (`src/orchestration/`, `src/graph.py`) | Hub-and-spoke graph, router, loop guard, human gate, runner with tracing and access policy, context strategy and metrics, handoff contract, scenarios, README diagram, integration of every agent, telemetry page |
| Guardrails and ethics | Supriya Patil | Intake (`src/agents/intake_agent.py`) | Intake script and agent, plain-language explanations, go back / change answer, "not sure" and skip, volunteered-SSN handling, alarms for advice, a spouse who died, a third party and pressure, guardrail tests, the accessible taxpayer chat (including the W-2 photo step), the volunteer dashboard (including the W-2 check) and the start page |
| Agent memory | JiWon Park | Document Extraction (`silverfile_extraction/`, `src/p3/`) | W-2 reading with a vision model into typed records, identifier screening, per-document volunteer approval, SQLite checkpointer and case memory, synthetic W-2 fixtures, API-key handling |
| Inter-agent communication | Matthew Suruadji | Eligibility & Rules (`src/agents/rules.py`) | `docs/policy.md` with numbered sections, eligibility, filing status, line 12d, scope screening, a citation on every decision, the Intake-to-Rules fact contract, decision-table tests |
| Security | Sahana Jay | Computation (`src/agents/computation.py`) | Tax tools over MCP, provenance format, the draft 1040-SR with click-to-see sources, the 900-series SSN rule and redaction, prompt-injection containment, hash-chained audit log, retention and purge |
| MLOps/DevOps | Shruti Goel | Review/Audit (`src/agents/review.py`) | Review agent (nine checks) and its send-back, CI, Dockerfile and Docker Compose, eval cases and runner, demo write-ups, `run.py`, the grader guide, the fresh-clone test, the implementation notes |

All six focus areas in the brief have an owner.

## How it works
Six agents, one hub. The **orchestrator** is the only thing that chooses the next hop and decides when to
stop; it does not extract, compute, or talk to the user. The other five (Intake, Document Extraction,
Eligibility & Rules, Computation, Review/Audit) never call each other: each returns a state update plus
a handoff request, which the orchestrator validates. Every agent call goes through one wrapper
(`src/orchestration/runner.py`) that scopes what the agent can see, enforces its read/write/tool
allow-lists, and writes a JSONL trace to `traces/`.

**Why hub-and-spoke:** one place decides the next hop, raises escalations, logs every handoff and stops loops, so
the business rules are enforced once instead of in every agent; and six people could build their agents in parallel
against one contract ([docs/handoff-contract.md](docs/handoff-contract.md)).

What the graph demonstrates:
- **Conditional routing:** the next hop is a pure function of state (`src/orchestration/router.py`).
- **Parallel branch:** extraction fans out one worker per document and merges with an order-independent reducer.
- **Bounded cycle:** Review sends work back to Computation, at most 3 times by default, then a human decides
  (`tests/test_review_loop.py`).
- **Loop guard:** a pathological handoff loop escalates to a human (`src/orchestration/guard.py`; triggered by an
  agent that never finishes in `tests/test_loop_guard.py`).
- **Human in the loop:** a LangGraph interrupt for out-of-scope items, unresolved conflicts, 1099-R box 2b,
  tax-advice requests, filing-status ambiguity (such as a spouse who died), and signs of exploitation.
- **Context management:** each agent gets the smallest view it needs
  ([decision record](docs/decisions/001-context-strategy.md), [measurements](docs/metrics.md)).

<!-- graph:start -->
```mermaid
---
config:
  flowchart:
    curve: linear
---
graph TD;
	__start__([<p>__start__</p>]):::first
	orchestrator(orchestrator)
	human(human)
	intake(intake)
	extraction(extraction)
	rules(rules)
	computation(computation)
	review(review)
	__end__([<p>__end__</p>]):::last
	__start__ --> orchestrator;
	computation --> orchestrator;
	extraction --> orchestrator;
	human --> orchestrator;
	intake --> orchestrator;
	orchestrator -. &nbsp;end&nbsp; .-> __end__;
	orchestrator -.-> computation;
	orchestrator -.-> extraction;
	orchestrator -.-> human;
	orchestrator -.-> intake;
	orchestrator -.-> review;
	orchestrator -.-> rules;
	review --> orchestrator;
	rules --> orchestrator;
	classDef default fill:#f2f0ff,line-height:1.2
	classDef first fill-opacity:0
	classDef last fill:#bfb6fc
```
<!-- graph:end -->

*Generated from the compiled graph by `python -m scripts.draw_graph`; every agent returns to the orchestrator
(solid), and only the orchestrator chooses the next hop (dotted). Also as an image: [docs/graph.png](docs/graph.png).*

## The six agents
Only Document Extraction calls a model; the other five are deterministic Python. What each agent reads and writes,
and the handoff format: [docs/handoff-contract.md](docs/handoff-contract.md).

### Orchestrator (Francesca)
Picks every next hop and owns the human gate (see "How it works" above).
- **Only it decides:** agents return a handoff request; the orchestrator validates it and chooses the next hop.
- **Never does the work:** it never extracts, computes or talks to the taxpayer.
- **Safe ending:** a case cannot end without a filing status and an eligibility verdict (`ELIGIBILITY_UNDECIDED`).

### Intake (Supriya)
The only agent that talks to the taxpayer ([docs/intake-script.md](docs/intake-script.md)).
- **One question at a time,** in six parts, in plain language; questions that do not apply are skipped.
- **Uncertainty and corrections:** "I'm not sure", "skip for now" and "talk to a volunteer" are always accepted; "go back" or a correction
  ("actually I was married") re-asks a question and keeps the old answer in the history.
- **Dates** are read back before they are saved; a date that could be read two ways is never guessed.
- **Typed amounts:** asks the SSA-1099, 1099-INT and 1099-DIV amounts right after "yes" to the form, saved as `direct user input`.
- **Alarms:** a request for tax advice, a spouse who died in 2025, someone else answering, or pressure about money or the
  refund. Only test SSNs are accepted; a real-looking one is refused and never saved.
- **Stuck answers:** an answer not understood after 3 tries is noted for a volunteer.
- **Accessibility:** the chat page is built for older adults: large text (22px+), strong contrast, big buttons, a progress list with
  "Change" buttons, and a saved session to come back to.

### Document Extraction (JiWon)
Reads W-2 photos only, with a vision model (OpenAI or Anthropic, whichever key is in `.env`, OpenAI first).
- **Volunteer check:** the taxpayer adds the photo in the chat, and a volunteer checks every amount on the dashboard
  before it is used (`EXTRACTION_REVIEW`). Each document is approved separately; a correction updates the record and
  keeps the original.
- **Typed records with evidence:** the result uses `extracted[doc_id].fields.box_1` etc., with the team's five
  provenance fields. Shared values are numeric; internal records keep decimal strings and source evidence.
- **Wired into the graph:** `src/agents/extraction.py` calls a registered P3 tool, rather than returning a hard-coded
  amount; one worker runs per document, in parallel.
- **Shared service:** the chat and the dashboard share one extraction service and the saved sessions
  (`src/ui/app_service.py`, `src/p3/shared_service.py`).
- **Tokens:** the runner records the provider's actual token usage for image reading; other agents' counts are
  labelled estimates.
- **Offline tests:** deterministic synthetic text fixtures; no key needed.
- **Privacy limits:** use **fictional test documents only**. The whole image is saved locally after your
  confirmation, then sent to the provider. Identifier screening happens after the image is sent, so it is not
  redaction and cannot guarantee a real identifier is blocked. Calls may be charged to your provider account; OpenAI
  requests use `store=False`, which does not guarantee zero retention.
- **Developer workbench:** the standalone W-2 workbench (`app.py`, started by `start.py` or `START_WINDOWS.cmd`) tests
  the extraction component on its own. It is not part of the app and is not started by Docker; use it with a new case
  ID and your own key in `.env`. Details: [P3_INTEGRATION.md](docs/P3_INTEGRATION.md),
  [P3_CHANGED_FILES.md](docs/P3_CHANGED_FILES.md), [VALIDATION.md](docs/VALIDATION.md).

### Eligibility & Rules (Matthew)
Decides from Intake's answers and the extracted documents, citing a numbered section of
[docs/policy.md](docs/policy.md) for every decision.
- **Eligibility:** born before January 2, 1961 (on a joint return, one spouse is enough).
- **Filing status** and the **line 12d** box count (65 or older, blind, for each spouse).
- **Scope:** anything out of scope stops the case for a volunteer, including a 1099-R with box 2b checked.
- **Never guesses:** a missing or "not sure" answer is never guessed (`ANSWER_UNCERTAIN`); saying "no" to a form that was uploaded
  raises `SOURCE_CONFLICT`.
- **Contract with Intake:** the fact names it reads are in [docs/intake-rules-contract.md](docs/intake-rules-contract.md).

### Computation (Sahana)
Fills lines 1a–37 of the draft, in the order the lines depend on each other (income, taxable Social Security,
AGI, standard and senior deductions, tax, payments, then the refund or amount owed).
- **No arithmetic of its own:** every number comes from a tax tool served over MCP (`src/tax_math_mcp.py`):
  standard deduction, senior deduction, taxable Social Security, income tax, sums and differences. The tool list
  lives once, in `src/tax_tools.py`, and `tests/test_computation_no_arithmetic.py` fails if arithmetic appears.
- **Provenance on every line** (value, formula, inputs, source, tool); a typed amount says `direct user input` and
  who entered it. If a form was also read from a document, the document wins, so nothing is counted twice.
- **No quiet zeros:** a form whose amounts were not read is marked `NOT READ` on its lines and the draft warns.
- **No silent fallback:** if the tool server cannot start, the case stops as `halted_by_error`.
- **Defensive escalations** (Rules should catch these first): a 1099-R whose taxable amount is not determined,
  an out-of-scope 1099, a taxpayer who can be claimed as a dependent, or a separately filing spouse who itemizes.
- **The draft 1040-SR** (`src/draft_form.py`): every amount expands to its formula, inputs, source and tool, with the
  filing status and who set it, Review's findings and every volunteer decision. `python -m scripts.render_draft`
  writes sample drafts to `demo/`.

### Review/Audit (Shruti)
Tries to prove the draft wrong before a volunteer sees it, and never corrects it itself.
- **Nine checks:** **scope** (an out-of-scope item on the draft raises an alarm), **provenance** (every amount has its record),
  **typed amounts** (each matches the taxpayer's answer), **sources** (each line matches its document);
  **recalculation** with the same tax tools, independently of Computation, and **totals**;
  **contradictions**, **completeness**, and **citations** (every `docs/policy.md` section Rules cites must exist).
- **Send-back:** any error sends the draft back to Computation with the findings, at most 3 rounds; then a
  volunteer decides. Warnings are recorded but do not send it back.

## Human in the loop
An agent raises a flag; the orchestrator sends the case to the human gate (`src/orchestration/human.py`), a
LangGraph `interrupt()`. A volunteer resolves it on the dashboard with their name and a note (required to continue),
and the graph resumes with `Command(resume=...)`.

| Condition | Raised by | The volunteer may |
|---|---|---|
| Out-of-scope item (Schedule A/C/D/E, 1099-NEC, digital assets, foreign income, amended, prior-year or state returns) | Rules, Extraction, Computation, Review (safety net) | Stop only |
| An answer contradicts a document (`SOURCE_CONFLICT`) | Rules | Continue with the right value, or stop |
| 1099-R with box 2b checked | Extraction, Rules, Computation | Stop only |
| Request for tax advice | Intake | Continue (question noted) or stop |
| Filing status unclear, e.g. a spouse died in 2025 | Intake, Rules | Continue with a filing status, or stop |
| Signs of exploitation or third-party pressure | Intake | Stop only |
| Also: an answer "not sure", a W-2 to check, income not read, the loop guard, the review bound | Rules, Extraction, Orchestrator | Depends on the condition |

## Provenance, security and privacy
- **Provenance:** every amount has `value, formula, inputs, source, tool`, and the runner rejects an amount without
  one. Click any amount on the draft to see it ([docs/provenance.md](docs/provenance.md)).
- **SSNs:** only test SSNs 900–999. A real-looking one is removed from every message as it enters the state, even if
  a page forgot to check it.
- **Traces and notes:** traces hold field names, never values; identifiers (SSN, EIN, email, phone) in escalation reasons
  and volunteer notes are redacted before they are saved.
- **Prompt injection:** document text is treated as data. Instruction-like text is flagged for a volunteer, and an
  agent that obeyed it still cannot write outside its allow-list or add an amount without provenance
  (`tests/test_prompt_injection.py`).
- **Audit log:** one append-only, hash-chained log per case (who decided what, never answers or amounts);
  `AuditLog.verify()` detects an entry edited or removed from the middle.
- **Retention:** a case idle 30 days expires and is deleted with `python -m scripts.purge_cases --expired`
  (schedule it); `--case <ID>` deletes one case everywhere.
- **Keys:** read only from `.env` (never committed; see `.env.example`); the app does not ask for a key on screen, and
  keys are never placed in state, traces or exported records.
- **Local only:** the app is served on this computer only (`127.0.0.1`), because the dashboard and `/telemetry` have
  no login. Case IDs are not secrets.

Details and limits: [docs/security.md](docs/security.md).

## Memory and context
- **Saved sessions:** a SQLite checkpointer (`runtime/team_checkpoints.sqlite`) saves the whole case after every step;
  the case ID is the LangGraph thread ID, so a taxpayer can come back another day.
- **Context strategy:** each agent gets a scoped view of state, Intake the last 6 messages plus the structured facts,
  and a deterministic rolling summary. On 30 turns and 12 documents it cuts estimated input tokens 17×
  ([docs/metrics.md](docs/metrics.md)); `--no-context-strategy` turns it off for measurement.

## Running it in more detail
**Docker Compose** keeps saved cases, uploaded photos, traces and the audit log in Docker volumes:

```
docker compose up --build                # start page http://localhost:8501 (telemetry: /telemetry)
docker compose down                      # stop; saved cases are kept
docker compose down -v                   # stop and delete all saved cases, uploads and traces
docker compose exec app python -m scripts.purge_cases --expired   # retention: delete expired cases
```

**Plain Docker:**

```
docker build -t silverfile .
docker run --rm silverfile                                    # a clean case to "DRAFT READY"
docker run --rm silverfile pytest -q                          # all tests, inside the container
docker run --rm -p 127.0.0.1:8501:8501 \
  -v silverfile-runtime:/app/runtime -v silverfile-traces:/app/traces \
  -v "$PWD/.env:/app/.env:ro" \
  silverfile streamlit run src/ui/silverfile_home.py
```

- Mount both volumes, or the case history is lost when the container is replaced.
- The app reads the key from the `.env` file itself, not from environment variables, so `--env-file` is not enough:
  mount the file read-only as above. Fill it in first: it is read once, when the app starts.
- Start the chat and the dashboard in one container (the start page), so they share the saved sessions.

**Scenarios in the terminal** (offline; each writes a trace to `traces/`):

```
.venv/bin/python -m scripts.run_scenarios clean               # a clean case to "DRAFT READY"
.venv/bin/python -m scripts.run_scenarios interrupt           # pauses for a human, then resumes
.venv/bin/python -m scripts.run_scenarios spouse-died         # filing-status ambiguity, volunteer supplies the status
.venv/bin/python -m scripts.run_scenarios clean --no-context-strategy   # every agent gets the full state
.venv/bin/python -m scripts.measure_context                   # regenerates docs/metrics.md
.venv/bin/python -m scripts.draw_graph                        # regenerates the diagram above
```

These use a short stand-in Intake so they stay deterministic; the chat always uses the real one.

**Telemetry** (read-only, staff only, no login): cases by outcome, time and tokens per agent, escalations, review
send-backs, safety alerts and the audit tamper check, from the traces and the audit log. In the app:
http://localhost:8501/telemetry. Spec: [docs/telemetry-dashboard-spec.md](docs/telemetry-dashboard-spec.md).

**A real W-2 reading** (one paid call; fictional fixtures only; key from `.env`):

```
.venv/bin/python -m scripts.verify_chat_extraction --provider anthropic     # or --provider openai
```

## Tests, evals and CI
- `pytest -q` runs every test, offline and without a key, including the extraction tests (`tests_p3`). Required ones:
  `tests/test_merge_order.py` and `tests/test_decision_table.py`.
- `python -m evals.runner` runs the 15 end-to-end cases in [evals/cases.json](evals/cases.json) and prints PASS, FAIL
  or PENDING for each. How to read and add them: [evals/README.md](evals/README.md).
- CI (`.github/workflows/ci.yml`) runs on every push and pull request (Python 3.11): the tests and evals, a Docker
  build that runs them inside the image, and a Docker Compose job that checks every page opens, cases survive new
  containers, and a W-2 photo goes from the chat through the volunteer's check to the draft.
- The fresh-clone run: [docs/fresh-clone-test.md](docs/fresh-clone-test.md).

## Layout
| Path | What |
|---|---|
| `run.py` | One entry point: `app`, `check`, `demo` |
| `src/state.py` | The shared state contract (fields, reducers, escalation conditions) |
| `src/graph.py` | The hub-and-spoke graph |
| `src/orchestration/` | The Orchestrator: router, loop guard, human gate, runner and tracing, access policy, context views |
| `src/agents/` | Intake, Document Extraction, Rules, Computation and Review (with the Orchestrator, all six are real) |
| `src/memory.py` | Saved sessions: checkpointer and resume summary |
| `src/ui/` | Start page, taxpayer chat, volunteer dashboard, telemetry page |
| `src/tax_math_mcp.py`, `src/mcp_client.py` | The tax tools' MCP server and client |
| `silverfile_extraction/`, `src/p3/` | W-2 reading, case memory, the shared extraction service |
| `data/` | `generate_fixtures.py` and the synthetic W-2 fixtures (`fixtures/`, with `expected.json`) |
| `evals/` | `cases.json` and the runner |
| `tax_math.py`, `provenance.py`, `security.py`, `document_security.py` | Tax math, provenance records, SSN and PII handling, document text handling |
| `computation_agent.py` | A standalone computation coordinator, kept with its test |
| `app.py`, `start.py`, `START_WINDOWS.cmd` | The standalone W-2 workbench (developer tool, not the app) |
| `tests/`, `tests_p3/`, root `test_*.py` | Tests |
| `scripts/` | Scenarios, metrics, diagram, purge, real-reading check |
| `demo/` | The two demo cases, their W-2 images and sample drafts |
| `Dockerfile`, `docker-compose.yml` | The image and the Compose app |
| `.github/workflows/ci.yml` | CI |
| `docs/` | See below |

## Documents
| Document | What |
|---|---|
| [for-graders.md](docs/for-graders.md) | How to run and check everything |
| [IMPLEMENTATION_NOTES.md](docs/IMPLEMENTATION_NOTES.md) | Where each requirement lives, design patterns, decisions, limitations |
| [handoff-contract.md](docs/handoff-contract.md) | What each agent reads and writes; the handoff format |
| [policy.md](docs/policy.md) | The rules corpus Rules cites |
| [intake-script.md](docs/intake-script.md), [answer-names.md](docs/answer-names.md), [intake-rules-contract.md](docs/intake-rules-contract.md) | Intake's questions; the names its answers are saved under; the facts Rules reads |
| [evals/README.md](evals/README.md) | The eval cases: how to read and add them |
| [provenance.md](docs/provenance.md), [security.md](docs/security.md) | Provenance records; security and privacy |
| [decisions/](docs/decisions/), [metrics.md](docs/metrics.md) | Decision records; context measurements |
| [AI_DISCLOSURE.md](docs/AI_DISCLOSURE.md), [AI_USE_LOG.md](docs/AI_USE_LOG.md) | How AI was used, per person and session |
| [STATUS.md](docs/STATUS.md) | Project status |

## Known limitations
- A 1099-R stops for a volunteer when box 2b is checked or its taxable amount is not determined.
- SSA-1099, 1099-INT and 1099-DIV are not read from photos; Intake asks their amounts.
- Someone who says they lived in the US all year but is dual-status for another reason is not detected.
- The deceased spouse's age is not asked, so a joint return counts only the taxpayer's 65+ box.
- Intake recognises phrasings by patterns, so some are only caught at a later question; after 3 tries a question is
  noted for a volunteer.
- A W-2 box a volunteer corrected still shows Document Extraction as its source; the change is in the audit log.
- No login: the dashboard and telemetry are for this computer only, with test data.
- The checkpoint database is not encrypted; redaction is regex-based and does not cover names or addresses.
- The audit log's hash chain detects an edited entry, not deleted final entries.
- Context metrics are estimates of prompt size, not billed tokens.

More, with the reasons: [docs/IMPLEMENTATION_NOTES.md](docs/IMPLEMENTATION_NOTES.md#5-known-limitations).

## Contributing
- Feature branches and pull requests reviewed by a teammate; never push to `main`. Run `pytest` before every commit.
- Secrets live only in `.env`; keep `.env.example` current. Never commit `.env`, `runtime/` or traces.
- If you own an agent, read [docs/handoff-contract.md](docs/handoff-contract.md) first.
