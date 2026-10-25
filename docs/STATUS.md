# Status: orchestration (Person 1)

Updated at the end of every phase. Branch: `orchestration-setup`.

## Done
- **Phase 1, scaffold:** state contract, hub-and-spoke graph, runner with JSONL tracing, five stub agents, scoped views, bounded orchestrator view, clean case runs end to end.
- **Phase 2, routing and HITL:** full routing table with decision-table test, interrupt/resume for all six conditions, stop-only rules, required notes, human-supplied resolutions, access-control tests.
- **Phase 3, parallelism and loops:** parallel extraction (Send fan-out, order-independent reducers for `extracted`, `handoff_request` and `escalation`, with simultaneous escalations queued rather than lost), bounded review loop (default 3, clears the stale verdict), loop guard (state repeated / same hop repeated). 124 tests.
- **Phase 4, context management:** scoped and narrowed views, Intake chat window (6), deterministic rolling summary, `--no-context-strategy`, long-session scenario (30 turns, 12 documents), `scripts/measure_context.py` and `docs/metrics.md`, full decision record. Orchestrator control channel (guard history and review findings kept out of its view). Spouse-died demo (eval case 2). 149 tests.
- `docs/handoff-contract.md` for agent owners.

## In progress
- Waiting for review of Phase 4 (and merge of the Phase 3 PR, which Phase 4 is stacked on).

## Next
- **Phase 5:** README run instructions and graph diagram generated from the compiled graph.
- Possible follow-up (not built): retrieve only the facts relevant to Intake's current question, so its view stops growing with the number of facts.

## Open questions
- **For the instructor:** the assignment's context section talks about "10 invoices", which does not match a tax project. We are treating it as "a long session or a batch of many documents". Is that acceptable?
- **For the Review owner:** `send_back_to` currently supports only `computation`; a request for `rules` is routed to computation and recorded. Sending work back to Rules would also invalidate computed lines; do we want that path? Also: Review must return exactly `pass` or `fail`.
- **Decided, please confirm:** `LOOP_GUARD` and `REVIEW_BOUND_EXCEEDED` are stop-only (a human may not "continue" past a failed review or a loop).
- **Branches:** `orchestration-phase3` (PR open) holds Phase 3; `orchestration-phase4` is stacked on it. Open the Phase 4 PR against `main` after Phase 3 merges.
- **For the memory owner:** the checkpointer is `InMemorySaver` (`SqliteSaver` optional); it needs replacing for persistence across restarts.
