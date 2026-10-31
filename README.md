# SilverFile (multiagent-tax-system)

A multi-agent system, built in LangGraph (Python), that helps prepare a **draft** US Form 1040-SR (tax year 2025)
for seniors, and keeps a record of where every number came from. A Kushim volunteer checks the draft; nothing is
ever filed.

Five business rules are enforced in code, not only in prompts:
- **Never file anything.** The output is a draft plus an audit record for a human.
- **Never give tax advice.** A request for advice is noted for a volunteer and the case pauses.
- **Never state an unsourced dollar amount.** Every amount carries a provenance record; the runner rejects one without it.
- **Always route the escalation cases to a human** through a LangGraph interrupt ([Human in the loop](#human-in-the-loop)).
- **Handle only the in-scope return profile.** Anything else escalates. Only test SSNs (900–999) and fictional documents.

## Quick start
Python 3.11 or newer, or Docker. Full steps for a grader: [docs/for-graders.md](docs/for-graders.md).

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
[demo/eval_case_2.md](demo/eval_case_2.md) (a human-in-the-loop event, resolved). A key is only needed to read W-2
photos; without one the chat says a volunteer will help.

## Team and focus areas
Each person owned one agent and one focus area of the assignment.

| Focus area | Person | Agent | What they built |
|---|---|---|---|
| Task division and management | Francesca Rondinella | Orchestrator (`src/orchestration/`, `src/graph.py`) | Hub-and-spoke graph, router, loop guard, human gate, runner with tracing and access policy, context strategy and metrics, handoff contract, scenarios, README diagram, integration of every agent, telemetry page |
| Guardrails and ethics | Supriya Patil | Intake (`src/agents/intake_agent.py`) | Intake script and agent, plain-language explanations, go back / change answer, "not sure" and skip, volunteered-SSN handling, alarms for advice, a spouse who died, a third party and pressure, guardrail tests, the accessible taxpayer chat, volunteer dashboard and start page |
| Agent memory | JiWon Park | Document Extraction (`silverfile_extraction/`, `src/p3/`) | W-2 reading with a vision model into typed records, identifier screening, per-document volunteer approval, SQLite checkpointer and case memory, synthetic W-2 fixtures, API-key handling |
| Inter-agent communication | Matthew Suruadji | Eligibility & Rules (`src/agents/rules.py`) | `docs/policy.md` with numbered sections, eligibility, filing status, line 12d, scope screening, a citation on every decision, the Intake-to-Rules fact contract, decision-table tests |
| Security | Sahana Jay | Computation (`src/agents/computation.py`) | Tax tools over MCP, provenance format, the draft 1040-SR with click-to-see sources, the 900-series SSN rule and redaction, prompt-injection containment, hash-chained audit log, retention and purge |
| MLOps/DevOps | Shruti Goel | Review/Audit (`src/agents/review.py`) | Review agent (nine checks) and its send-back, CI, Dockerfile and Docker Compose, eval cases and runner, demo write-ups, `run.py`, the grader guide, the fresh-clone test, the implementation notes |

## How it works
Six agents, one hub. The **orchestrator** is the only thing that chooses the next hop and decides when to
stop; it does not extract, compute, or talk to the user. The other five (Intake, Document Extraction,
Eligibility & Rules, Computation, Review/Audit) never call each other: each returns a state update plus
a handoff request, which the orchestrator validates. Every agent call goes through one wrapper
(`src/orchestration/runner.py`) that scopes what the agent can see, enforces its read/write/tool
allow-lists, and writes a JSONL trace to `traces/`.

What the graph demonstrates:
- **Conditional routing:** the next hop is a pure function of state (`src/orchestration/router.py`).
- **Parallel branch:** extraction fans out one worker per document and merges with an order-independent reducer.
- **Bounded cycle:** Review sends work back to Computation, at most 3 times by default.
- **Loop guard:** a pathological handoff loop escalates to a human.
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
| Agent | What it does | Never does |
|---|---|---|
| **Orchestrator** | Picks every next hop, owns the human gate, ends the case only with a filing status and an eligibility verdict | Extract, compute, or talk to the taxpayer |
| **Intake** | The only agent that talks to the taxpayer: [24 plain-language questions](docs/intake-script.md), one at a time, with "not sure", go back and skip; asks the SSA-1099, 1099-INT and 1099-DIV amounts; raises alarms for tax-advice requests, a spouse who died, a third party answering, or pressure | Arithmetic, or explain tax rules |
| **Document Extraction** | Reads W-2 photos with a vision model (OpenAI or Anthropic) into typed records with source evidence; a volunteer checks every W-2 before it is used | Interpret tax rules |
| **Eligibility & Rules** | 1040-SR eligibility, filing status, line 12d, scope; every decision cites a section of [docs/policy.md](docs/policy.md) | Guess a missing or uncertain answer |
| **Computation** | Fills lines 1a–37 only through the tax tools served over MCP (`src/tax_math_mcp.py`); every line has a provenance record | Arithmetic of its own |
| **Review/Audit** | Nine checks: scope, provenance, typed amounts, sources, independent recalculation, totals, contradictions, completeness, citations; errors go back to Computation, an out-of-scope line raises an alarm | Correct the draft itself |

Only Document Extraction calls a model. Intake, Rules, Computation and Review are deterministic Python. What each
agent reads and writes, and the handoff format: [docs/handoff-contract.md](docs/handoff-contract.md).

## Human in the loop
An agent raises a flag; the orchestrator sends the case to the human gate (`src/orchestration/human.py`), a
LangGraph `interrupt()`. A volunteer resolves it on the dashboard with their name and a required note, and the
graph resumes with `Command(resume=...)`.

| Condition | Raised by | The volunteer may |
|---|---|---|
| Out-of-scope item (Schedule A/C/D/E, 1099-NEC, digital assets, foreign income, amended, prior-year or state returns) | Rules, Extraction, Review (safety net) | Stop only |
| An answer contradicts a document (`SOURCE_CONFLICT`) | Rules | Continue with the right value, or stop |
| 1099-R with box 2b checked | Extraction, Rules, Computation | Stop only |
| Request for tax advice | Intake | Continue (question noted) or stop |
| Filing status unclear, e.g. a spouse died in 2025 | Intake, Rules | Continue with a filing status, or stop |
| Signs of exploitation or third-party pressure | Intake | Stop only |
| Also: an answer "not sure", a W-2 to check, income not read, the loop guard, the review bound | Rules, Extraction, Orchestrator | Depends on the condition |

## Provenance, security and privacy
- **Provenance:** every amount has `value, formula, inputs, source, tool`; a typed amount says `direct user input`.
  Click any amount on the draft to see it. [docs/provenance.md](docs/provenance.md).
- **Security** ([docs/security.md](docs/security.md)): only test SSNs 900–999 (real-looking ones are removed from
  every message); traces hold field names, never values; document text is treated as data (prompt-injection
  containment); a hash-chained audit log per case; retention with `python -m scripts.purge_cases --expired`.
- **Keys:** read only from `.env` (never committed; see `.env.example`), never placed in state, traces or records.
- **Local only:** the app is served on this computer only (`127.0.0.1`), because the dashboard and `/telemetry` have
  no login. Case IDs are not secrets.

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

## Document extraction (P3)
Extraction reads W-2 photos only. In the app, the taxpayer adds the photo in the chat and a volunteer checks every
amount on the dashboard before it is used (`EXTRACTION_REVIEW`). Each document is approved separately; a correction
updates the record and keeps the original. The chat and the dashboard share one extraction service and the saved
sessions (`src/ui/app_service.py`, `src/p3/shared_service.py`).

The standalone W-2 workbench (`app.py`, started by `start.py` or `START_WINDOWS.cmd`) is a developer tool for the
extraction component on its own. It is not part of the app and is not started by Docker; use it with a new case ID
and your own key in `.env`. Details: [P3_INTEGRATION.md](docs/P3_INTEGRATION.md),
[P3_CHANGED_FILES.md](docs/P3_CHANGED_FILES.md) and [VALIDATION.md](docs/VALIDATION.md).

**Privacy limits.** Use **fictional test documents only**. The whole image is saved locally after your confirmation,
then sent to the provider (OpenAI or Anthropic, whichever key is in `.env`, OpenAI first). Identifier screening happens
after the image is sent, so it is not redaction and cannot guarantee a real identifier is blocked. Calls may be charged
to your provider account; OpenAI requests use `store=False`, which does not guarantee zero retention.

## Layout
| Path | What |
|---|---|
| `run.py` | One entry point: `app`, `check`, `demo` |
| `src/state.py` | The shared state contract (fields, reducers, escalation conditions) |
| `src/graph.py` | The hub-and-spoke graph |
| `src/orchestration/` | The Orchestrator: router, loop guard, human gate, runner and tracing, access policy, context views |
| `src/agents/` | Intake, Document Extraction, Rules, Computation and Review |
| `src/memory.py` | Saved sessions: checkpointer and resume summary |
| `src/ui/` | Start page, taxpayer chat, volunteer dashboard, telemetry page |
| `src/tax_math_mcp.py`, `src/mcp_client.py` | The tax tools' MCP server and client |
| `silverfile_extraction/`, `src/p3/` | W-2 reading, case memory, the shared extraction service |
| `data/` | `generate_fixtures.py` and the synthetic W-2 fixtures (`fixtures/`, with `expected.json`) |
| `evals/` | `cases.json` and the runner |
| `tests/`, `tests_p3/` | Tests |
| `scripts/` | Scenarios, metrics, diagram, purge, real-reading check |
| `demo/` | The two demo cases, their W-2 images and sample drafts |
| `docs/` | See below |

## Documents
| Document | What |
|---|---|
| [for-graders.md](docs/for-graders.md) | How to run and check everything |
| [IMPLEMENTATION_NOTES.md](docs/IMPLEMENTATION_NOTES.md) | Where each requirement lives, design patterns, decisions, limitations |
| [handoff-contract.md](docs/handoff-contract.md) | What each agent reads and writes; the handoff format |
| [policy.md](docs/policy.md) | The rules corpus Rules cites |
| [intake-script.md](docs/intake-script.md), [intake-rules-contract.md](docs/intake-rules-contract.md) | Intake's questions; the fact names Rules reads |
| [provenance.md](docs/provenance.md), [security.md](docs/security.md) | Provenance records; security and privacy |
| [decisions/](docs/decisions/), [metrics.md](docs/metrics.md) | Decision records; context measurements |
| [AI_DISCLOSURE.md](docs/AI_DISCLOSURE.md), [AI_USE_LOG.md](docs/AI_USE_LOG.md) | How AI was used, per person and session |
| [STATUS.md](docs/STATUS.md) | Project status |

## Known limitations
- A 1099-R always stops for a volunteer; its taxable amount is not computed.
- SSA-1099, 1099-INT and 1099-DIV are not read from photos; Intake asks their amounts.
- Intake is rule-based: unusual wording can be missed (it re-asks, then notes it for a volunteer).
- No login: the dashboard and telemetry are for this computer only, with test data.
- The audit log's hash chain detects an edited entry, not deleted final entries.
- Context metrics are estimates of prompt size, not billed tokens.

More, with the reasons: [docs/IMPLEMENTATION_NOTES.md](docs/IMPLEMENTATION_NOTES.md#5-known-limitations).

## Contributing
- Feature branches and pull requests reviewed by a teammate; never push to `main`. Run `pytest` before every commit.
- Secrets live only in `.env`; keep `.env.example` current. Never commit `.env`, `runtime/` or traces.
- If you own an agent, read [docs/handoff-contract.md](docs/handoff-contract.md) first.
