# Status: orchestration (Person 1)

Updated at the end of every phase. Branch: `orchestration-setup`.

## Done
- **Phase 1, scaffold:** state contract, hub-and-spoke graph, runner with JSONL tracing, five stub agents, scoped views, bounded orchestrator view, clean case runs end to end.
- **Phase 2, routing and HITL:** full routing table with decision-table test, interrupt/resume for all six conditions, stop-only rules, required notes, human-supplied resolutions, access-control tests.
- `docs/handoff-contract.md` for agent owners.

## In progress
- **Phase 3:** parallel extraction (Send fan-out, order-independent reducer), bounded review loop, loop guard.

## Next
- **Phase 4:** context strategy (`context.py` views, rolling summary, selective recall), the decision record, the metrics script and `docs/metrics.md`.
- **Phase 5:** README run instructions and graph diagram.

## Open questions
- **For the instructor:** the assignment's context section talks about "10 invoices", which does not match a tax project. We are treating it as "a long session or a batch of many documents". Is that acceptable?
- **For the Review owner:** `send_back_to` currently supports only `computation`. Sending work back to Rules would also invalidate computed lines; do we want that path?
- **For the memory owner:** the checkpointer is `InMemorySaver` (`SqliteSaver` optional); it needs replacing for persistence across restarts.
