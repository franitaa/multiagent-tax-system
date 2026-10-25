# Status: orchestration (Person 1)

Updated at the end of every phase. Branch: `orchestration-setup`.

## Done
- **Phase 1, scaffold:** state contract, hub-and-spoke graph, runner with JSONL tracing, five stub agents, scoped views, bounded orchestrator view, clean case runs end to end.
- **Phase 2, routing and HITL:** full routing table with decision-table test, interrupt/resume for all six conditions, stop-only rules, required notes, human-supplied resolutions, access-control tests.
- **Phase 3, parallelism and loops:** parallel extraction (Send fan-out, order-independent reducers for `extracted`, `handoff_request` and `escalation`, with simultaneous escalations queued rather than lost), bounded review loop (default 3, clears the stale verdict), loop guard (state repeated / same hop repeated). 124 tests.
- `docs/handoff-contract.md` for agent owners.

## In progress
- Waiting for review of Phase 3 before starting Phase 4.

## Next
- **Phase 4:** context strategy (`context.py` views, rolling summary, selective recall), the decision record, the metrics script and `docs/metrics.md`.
- **Phase 5:** README run instructions and graph diagram.

## Open questions
- **For the instructor:** the assignment's context section talks about "10 invoices", which does not match a tax project. We are treating it as "a long session or a batch of many documents". Is that acceptable?
- **For the Review owner:** `send_back_to` currently supports only `computation`; a request for `rules` is routed to computation and recorded. Sending work back to Rules would also invalidate computed lines; do we want that path? Also: Review must return exactly `pass` or `fail`.
- **Decided, please confirm:** `LOOP_GUARD` and `REVIEW_BOUND_EXCEEDED` are stop-only (a human may not "continue" past a failed review or a loop).
- **For the memory owner:** the checkpointer is `InMemorySaver` (`SqliteSaver` optional); it needs replacing for persistence across restarts.
