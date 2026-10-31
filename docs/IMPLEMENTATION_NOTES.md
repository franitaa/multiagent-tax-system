# Implementation notes

How SilverFile is built, the decisions behind it, and what it does not do. For running it, see
[for-graders.md](for-graders.md); for what each agent reads and writes, see
[handoff-contract.md](handoff-contract.md).

## 1. Where each requirement lives
| Requirement | Where |
|---|---|
| Six agents, hub-and-spoke | `src/graph.py` (graph), `src/orchestration/orchestrator.py` (the hub), `src/agents/` (the five spokes) |
| Orchestrator picks every next hop | `src/orchestration/router.py`, `route()`: a pure function of a routing view, rules checked in order |
| One wrapper for every agent call | `src/orchestration/runner.py`: scoped view, read/write/tool allow-lists (`access.py`), output checks (`validate.py`), JSONL trace in `traces/`, token counts |
| Parallel branch and reducer | Extraction fans out one worker per document with `Send`; `merge_extracted` and `merge_escalation` in `src/state.py` give the same result in any arrival order (`tests/test_merge_order.py`) |
| Bounded review cycle | Review fails → Computation revises → Review again, at most `max_revisions` rounds (3 by default), then `REVIEW_BOUND_EXCEEDED` to a human |
| Loop guard | `src/orchestration/guard.py`: a repeated state, or the same agent more than 3 times in a row, escalates as `LOOP_GUARD` |
| Human in the loop | `src/orchestration/human.py`: a LangGraph `interrupt()`; the volunteer's answer resumes the graph with `Command(resume=...)` |
| Pause and resume across days | SQLite checkpointer (`runtime/team_checkpoints.sqlite`); `src/memory.py` reads a saved case back without restarting it |
| Provenance for every amount | `ProvenanceRecord` (`value, formula, inputs, source, tool`) in `src/state.py`; `validate.py` refuses a dollar amount in `computed` without one; [provenance.md](provenance.md) |
| Context management | `src/orchestration/context.py`, `view_for()`; `--no-context-strategy`; [decision 001](decisions/001-context-strategy.md), [metrics.md](metrics.md) |
| Rules corpus | [policy.md](policy.md); Rules cites its sections and Review checks each citation exists |
| Eval cases | `evals/cases.json` (15 cases), `evals/runner.py`; run in CI |
| Volunteer dashboard | `src/ui/volunteer_dashboard.py`; telemetry (bonus, read-only) in `src/ui/telemetry_dashboard.py` |

## 2. Design patterns
The code mostly uses LangGraph's own building blocks (`StateGraph`, reducers, `Send`, `interrupt`,
`Command`). Named, they are:

| Pattern | Where | Why |
|---|---|---|
| Mediator (supervisor) | The orchestrator; agents never call each other | One place decides the next hop, logs handoffs and stops loops |
| Proxy / interceptor | `runner.py` around every agent | Scoping, permissions and tracing cannot be skipped by an agent |
| Decision table (first match wins) | `route()` | Each rule is readable and unit-tested (`tests/test_decision_table.py`) |
| Circuit breaker | Loop guard and the review bound | A stuck case goes to a human instead of running forever |
| Memento | The checkpointer | A case can wait for a volunteer and resume later |
| Command | `Command(resume=...)` | The volunteer's decision is a value the graph resumes with |
| Reducer (order-independent fold) | `src/state.py` | Parallel workers can finish in any order |
| Evaluator–optimizer | Review → Computation → Review | An independent check sends findings back for a revision |
| Map-reduce | Parallel extraction | One worker per document, merged by the reducer |
| Least privilege | `access.py` `POLICY` and the `ToolBox` | An agent can only read, write and call what its allow-list names |
| Strategy | Context on/off; tax tools over MCP or in-process; OpenAI or Anthropic for the W-2 reading | Same interface, swappable behaviour |
| Dependency injection | `build_graph(agents=..., checkpointer=..., tool_registry=...)` | Tests swap in fakes (e.g. the offline W-2 reader) |
| Value object | `ProvenanceRecord` | Every amount carries its receipt |
| Pipeline of checks | Review: scope, provenance, sources, recompute, totals, contradictions, completeness, citations | Each check is a small function; adding one does not touch the others |

Not used, on purpose: agent class hierarchies (every agent is a plain `run(view, tools) -> dict`,
which LangGraph nodes need anyway), objects in state (state must stay plain data so the checkpointer
can save it), and an event bus (the trace file is the only consumer).

## 3. Implementation decisions
- **Only Document Extraction calls a model.** It reads the W-2 photo with OpenAI or Anthropic (the key
  comes from `.env` only). Intake, Rules, Computation and Review are deterministic Python, so an
  amount, a rule or a check never depends on a model's wording. Intake spots tax-advice requests and
  pressure by phrase patterns, and the human gate handles anything uncertain.
- **Arithmetic only through tools.** Computation and Review call the same tax tools
  (`calculate_standard_deduction`, `calculate_senior_deduction`, `calculate_taxable_social_security`,
  `calculate_income_tax`, plus `sum_amounts` and `subtract_amounts` for Computation), served over MCP
  by default (`src/tax_math_mcp.py`; `SILVERFILE_TOOL_TRANSPORT=local` runs them in-process). Review
  recomputes independently rather than trusting Computation's numbers.
- **Typed amounts count as sourced.** SSA-1099, 1099-INT and 1099-DIV are not read from photos; Intake
  asks their amounts, saved as `direct user input`, and the draft shows that source. A form whose
  amount is unknown pauses the case once for a volunteer (`INCOME_NOT_READ`) before Computation.
- **Every W-2 reading is checked by a volunteer** (`EXTRACTION_REVIEW`) before Computation uses it.
- **Stop-only escalations.** `OUT_OF_SCOPE`, `FORM_1099R_BOX_2B`, `EXPLOITATION_SIGNS`, `LOOP_GUARD`,
  `REVIEW_BOUND_EXCEEDED` and `ELIGIBILITY_UNDECIDED` can only be stopped, so a volunteer cannot push
  an out-of-scope or unsafe return through (`CONTINUABLE` in `human.py`). A continue needs a note, and
  for a filing-status question a filing status.
- **Real Intake on every entry point a person uses.** The 24-question Intake runs in the chat, the
  CLI and the evals' `real_intake` mode; the one-question stub stays the offline default for tests
  and the context metrics ([decision 002](decisions/002-demo-defaults-and-assumptions.md)).
- **"10 invoices" in the brief** was read as a long session plus many documents: 30 turns and 12
  documents in [metrics.md](metrics.md) (decision 002).
- **Security** is described in [security.md](security.md): only 900–999 test SSNs, real-looking ones
  removed from every message, traces hold field names only, a hash-chained audit log per case, and a
  purge command for retention.
- **Local only.** Docker Compose and `python run.py` serve the app on `127.0.0.1`, because the
  dashboard and telemetry have no login.

## 4. Testing and CI
- `python run.py check` runs `pytest` (1,376 tests) and the eval cases (15 pass, 0 fail, 0 pending).
- GitHub Actions (`.github/workflows/ci.yml`) runs on every push and PR: the tests and evals on Python
  3.11, a Docker build, and a Compose job that starts the app, opens every page, and takes a W-2
  photo from the chat through the volunteer's check to the draft, then purges the case.
- The tests that call a provider use an offline reader; the one real check is
  `python -m scripts.verify_chat_extraction --provider anthropic` (or `openai`), run by hand with a key.
- The fresh-clone run is recorded in [fresh-clone-test.md](fresh-clone-test.md).

## 5. Known limitations
- **1099-R always stops** for a volunteer: its taxable amount is not computed.
- **Dual status:** Intake asks whether the taxpayer lived in the US all year (Q23); "no" stops the case
  and "not sure" pauses it. Someone who answers "yes" but is dual-status for another reason is not
  detected ([policy.md §2.4](policy.md)).
- **Deceased spouse's age** is not asked, so a joint return counts only the taxpayer's 65+ box.
- **No login.** Case IDs are not secrets, volunteer names are not verified, and the dashboard is
  reachable from the start page; keep it on localhost.
- **Provenance after a volunteer's correction:** a W-2 box a volunteer corrected still shows Document
  Extraction as its source; the change itself is in the audit log.
- **Stored data:** the checkpoint database is not encrypted; redaction is regex-based and does not
  cover names or addresses; purges are not scheduled automatically.
- **Context metrics are estimates** (`ceil(len(json)/4)` of each view), because the agents measured
  are offline; the scoped curve is flatter but still grows with each new fact ([metrics.md](metrics.md)).

## 6. Differences from the brief's layout
- The rules corpus is `docs/policy.md`, not `data/policy.md`; Review, the tests and the docs all use it.
- The agents are in `src/agents/` and the orchestration pieces in `src/orchestration/`; W-2 extraction
  internals are in `src/p3/`.
- The demo W-2s are `demo/w2_image_1.jpg` and `demo/w2_image_2.jpg`, copies of
  `data/fixtures/w2_01.jpg` and `w2_02.jpg`.
