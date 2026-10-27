# Status: orchestration (Person 1)

Updated at the end of every phase. Branch: `orchestration-phase5` (stacked on `orchestration-phase4`).

## Done
- **Phases 1-3 (merged):** state contract, hub-and-spoke graph, runner with JSONL tracing, routing table, human interrupt with stop-only rules, parallel extraction with order-independent reducers, bounded review loop, loop guard.
- **Phase 4 (PR open):** scoped views, Intake chat window (6), deterministic rolling summary, `--no-context-strategy`, long-session scenario, `scripts/measure_context.py` and `docs/metrics.md`, full decision record, orchestrator control channel, spouse-died demo.
- **Phase 5:** README with run instructions and a diagram generated from the compiled graph (`scripts/draw_graph.py`, with a test that fails if it goes stale); plain `pytest` now collects the root-level tests too.
- **Orchestrator invariant:** a case can never end "complete" without a filing status and an eligibility verdict; it pauses with `ELIGIBILITY_UNDECIDED` (orchestrator-raised, stop-only) right after Rules.
- **Integration check of the real Intake with the real Rules** (`docs/intake-rules-contract.md`, `tests/test_e2e_intake.py`, `tests/test_rules_intake_contract.py`). Real Intake works in our graph (24-question interview, 6-message window, escalation of a spouse who died). Rules does not understand its output yet.

## In progress
- Review of the Phase 4 PR. Matthew is reworking Rules. Supriya's Intake PR (`feature/intake-agent`) is under review; my findings are listed below.

## Next
- **Wire in the real Intake (on hold):** point `AGENTS["intake"]` at `intake_agent.run` only after the Intake PR is merged *and* Rules is fixed. The chat page already builds its own graph with the real Intake (`chat_session.make_graph`), so the PR does not change the CLI scenarios.
- Wire Sahana's computation agent through the tool allow-list (`TOOLS` / `POLICY`); decide where PII redaction hooks in (suggestion: the runner).
- Find the Extraction and Review owners; both are still stubs.
- Possible follow-up (not built): give Intake only the facts relevant to its current question.

## Open questions
- **For Matthew (Rules), four things, all with failing tests that define "done":**
  1. Read the fact names Intake writes (`taxpayer_birth_date`, `spouse_died_2025`, ...); see the table in `docs/intake-rules-contract.md`.
  2. Parse Intake's `"yes"/"no"/"not_sure"` strings. Today `bool("no")` is `True`, so a taxpayer who answered "no" to blindness is counted as blind (2 boxes instead of 1).
  3. Use `facts["filing_status"]` (a volunteer's answer, source `human:...`) before deriving a status.
  4. Always return a non-empty `filing_status` and a boolean `in_scope` (the orchestrator now pauses otherwise), and raise a specific escalation when you can say why.
  5. **Raise `OUT_OF_SCOPE` from Intake's screening answers** (stocks, business, foreign income, digital assets, other forms): Intake only records them and Rules does not read them, so nobody escalates today (section 5 of the doc; 5 failing tests).
- **Intake PR review (for Supriya):** green (427 tests on her branch merged with `main`), contract-compliant, no secrets or non-9xx SSNs, no disk writes, bad input and impossible dates handled, chat page launches. To discuss: (a) exploitation detection missed 7 of 8 realistic phrasings ("making me do this", "being forced", "was told to", "keeps my refund", "not to tell anyone") and a missed phrase just re-asks forever, so consider an escalation after repeated misunderstandings; (b) a real-looking SSN is stripped only by the chat page, so a direct graph call leaves it in `state["messages"]` (needs a redaction hook at the graph boundary: orchestration and Sahana); (c) `dependents` (name, relationship, SSN) and `volunteer_notes` (the taxpayer's own words) sit in `facts`, which Rules reads in full (orchestration to narrow Rules' view).
- **For the instructor:** the assignment's context section talks about "10 invoices", which does not match a tax project. We are treating it as "a long session or a batch of many documents". Is that acceptable?
- **For the Review owner:** `send_back_to` supports only `computation`; Review must return exactly `pass` or `fail`.
- **Decided:** `LOOP_GUARD` and `REVIEW_BOUND_EXCEEDED` are stop-only.
- **For the memory owner:** the checkpointer is `InMemorySaver` (`SqliteSaver` optional); it needs replacing for persistence across restarts.
- **Process:** two Rules commits went straight to `main` without a PR. Suggest branch protection requiring PRs.
