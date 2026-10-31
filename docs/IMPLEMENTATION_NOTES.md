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
`Command`) and plain functions. Named, the patterns are:

**Multi-agent and control flow**
| Pattern | Where | Why |
|---|---|---|
| Mediator (supervisor, hub-and-spoke) | The orchestrator; agents never call each other | One place decides the next hop, logs handoffs and stops loops |
| Decision table / chain of responsibility | `route()` in `router.py`: rules checked in order, first match wins | Each rule is readable and unit-tested (`tests/test_decision_table.py`) |
| Functional core, imperative shell | `route()`, `apply_guard()` and `summarise()` are pure functions; the orchestrator node applies their result | The routing logic is tested without a graph |
| Evaluator–optimizer (critic and revise) | Review fails → findings in `pending_revision` → Computation revises → Review again | An independent check sends work back instead of passing a wrong draft |
| Map-reduce (fan-out, fan-in) | One extraction worker per document with `Send`, merged by reducers | Documents are read in parallel |
| Circuit breaker | `guard.py` (`LOOP_GUARD`) and the review bound (`REVIEW_BOUND_EXCEEDED`) | A stuck case goes to a human instead of running forever |
| Human-in-the-loop gate | `human.py`: `interrupt()`, then `Command(resume=...)` | A volunteer decides the escalation cases |
| Command | The volunteer's decision `{"decision", "note", "resolution", "reviewer"}` | The decision is a value the graph resumes with and the audit log records |
| Memento | The SQLite checkpointer | A case can wait for a volunteer and resume days later |
| Idempotent replay | `interrupt()` is the first statement of the human node | LangGraph re-runs the node from the top on resume, so nothing before it may have side effects |
| Fail-safe stop | `Runner._halt_on_error`: a tax-tool server that cannot start ends the case as `halted_by_error` | Nothing is computed from a missing tool; the case stops with a trace and an audit entry |

**State and data**
| Pattern | Where | Why |
|---|---|---|
| Reducer (order-independent fold) | `merge_extracted`, `merge_escalation`, `merge_request`, `append_list` in `src/state.py` | Parallel workers give the same state in any arrival order (`tests/test_merge_order.py`) |
| Priority queue | `merge_escalation`: the most severe flag is active, the rest wait in `queued`, sorted by `ESCALATION_PRIORITY` | No escalation is lost when two are raised at once |
| Optimistic concurrency (versioning) | `revision` in `merge_extracted`; `StaleRevisionError` in `silverfile_extraction/case_memory.py` | An old copy of a case cannot overwrite a newer one |
| Value object | `ProvenanceRecord` (`value, formula, inputs, source, tool`) | Every amount carries its receipt |
| Plain data state (DTO) | `SilverState` is a `TypedDict` of JSON-like values | Any checkpointer can save it |
| Projection (scoped views) | `view_for()`, `routing_view()` in `context.py` | Each agent sees only the fields it needs |
| Rolling summary | `summarise()` writes `session_summary` after each hop | Agents get a short summary instead of the whole history |
| Append-only log | `handoff_log`, `human_decisions`, `review_history`; Intake keeps old answers in `history` | Nothing that was decided is overwritten |
| Hash chain | `src/audit.py`: each entry's hash includes the previous one; `AuditLog.verify()` | An edited or removed entry in the middle is detected |

**Security**
| Pattern | Where | Why |
|---|---|---|
| Proxy / interceptor | `runner.py` around every agent call | Scoping, permissions, redaction and tracing cannot be skipped by an agent |
| Least privilege (capability object) | `POLICY` in `access.py` and the `ToolBox` | An agent can only read, write and call what its allow-list names |
| Allow-list | Test SSNs 900–999 only; `RULES_FACTS` for what Rules may see | Anything not listed is refused |
| Validation at the boundary | `check_update()` in `validate.py`: size, plain data, known handoffs and conditions, no amount without provenance | A misbehaving agent's output never reaches state |
| Sanitise on entry | The `append_messages` reducer removes real-looking SSNs from every message; the runner redacts free-text notes | Personal data is cleaned once, where it enters |
| Quarantine of untrusted input | `document_security.py`: document text labelled as data, control characters removed, instruction-like text flagged | A document cannot give the agents instructions |
| Time-to-live retention | `src/retention.py`, `scripts/purge_cases.py`: idle cases expire after 30 days, stray uploads after 24 hours | Personal data is not kept forever |

**Structure and wiring**
| Pattern | Where | Why |
|---|---|---|
| Uniform interface | Every agent is `run(view, tools) -> dict` | Agents are interchangeable and tested the same way |
| Registry (plugin) | `AGENTS` and `live_agents()` in `src/agents/__init__.py`; `TOOLS` in `access.py` | Swapping an agent or adding a tool is one entry |
| Factory function | `build_graph()`, `make_shared_service()`, `live_agents()` | One place builds a correctly wired graph |
| Dependency injection | `build_graph(agents=..., checkpointer=..., tool_registry=...)`; the injected W-2 reader | Tests swap in fakes (e.g. `FakeReader`) |
| Strategy | Context on/off (`--no-context-strategy`); tax tools over MCP or in-process (`SILVERFILE_TOOL_TRANSPORT`); OpenAI or Anthropic for the W-2 | Same interface, swappable behaviour |
| Adapter | `team_record()` in `src/p3/bridge.py` (the extraction record into the team's provenance shape); `McpToolClient` (MCP calls behind the same function names) | Two internal formats meet the team's contract |
| Remote proxy | `mcp_registry()`: each tax tool is a local callable that calls the MCP server | Computation and Review do not know where the tools run |
| Singleton (one per process) | `shared_client()` in `mcp_client.py` (lock-guarded); `get_service()` with `st.cache_resource` | One tool server and one service shared by every page |
| Memoisation | `policy_sections()` in `review.py` (`lru_cache`) | `policy.md` is read once |
| Mutex / atomic claim | `running()` in `chat_session.py`; locks in the runner, the audit log and the MCP client | A second tab cannot start a second run; parallel workers do not interleave a file |
| Stub / test double | The one-question Intake stub (offline default); `FakeReader` in the tests | Tests and metrics are short, deterministic and need no key |
| Read model (query side) | `src/telemetry.py` and `dashboard_data.py` read traces, the audit log and saved state; telemetry never writes | Dashboards cannot change a case except through the human gate |
| Pipeline of checks (specification) | Review: scope, provenance, direct input, sources, recompute, totals, contradictions, completeness, citations | Each check is a small function returning findings; adding one does not touch the others |

**Not used, on purpose:** agent class hierarchies (a plain `run(view, tools)` is what LangGraph nodes
need), objects in state (the checkpointer must be able to save it), and an event bus (the trace file
and the audit log are the only consumers).

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
- **Real Intake on every entry point a person uses.** The 24-question Intake runs in the chat (and
  the shared service the dashboard uses) and in the evals' `real_intake` mode; the one-question stub
  stays the offline default for the tests, the command-line demo cases (`scripts.run_scenarios`) and
  the context metrics ([decision 002](decisions/002-demo-defaults-and-assumptions.md)).
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
