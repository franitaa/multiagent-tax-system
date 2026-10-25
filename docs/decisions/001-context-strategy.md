# 001: Context strategy

Status: **draft, completed in Phase 4** (comparison of trimming vs summarisation vs selective recall, and measurements, are still to be written).

## Decision so far
Each agent receives a scoped view of state (`src/orchestration/context.py`), not the whole state. `--no-context-strategy` switches every view to the full state for measurement.

## The orchestrator's view is bounded
The orchestrator sees a compact routing view: status flags, counts, the escalation flag, the
pending review verdict, and at most the last 3 handoffs, each as `{step, to, reason}` with `reason`
cut to 60 characters. It never receives documents, chat, fact values, or id lists; "documents not
yet extracted" is passed as a single count (`n_docs_pending`).

Why: the first measurement of the Phase 1 clean case showed the orchestrator's input growing from
about 83 to about 220 estimated tokens over a short run, because the view carried full handoff-log
entries and id lists that grow with the number of documents. The orchestrator is called after every
agent, so any growth in its view is paid on every hop. Bounding it keeps its per-call cost constant
regardless of session length or batch size.

### Deterministic-only inputs stay out of the view
The orchestrator is deterministic Python (the router plus the loop guard), not a model. Two things
it needs would bloat a model-facing view and are useless to a model: the loop guard's fingerprint
history (up to 24 hashes) and a failed review's findings (copied, uninterpreted, into the revision
request). They reach the code through a separate `control` channel (`View.control`,
`context.control_view`). It is not a key of the view, so it is not counted in the token estimate,
and the trace lists it separately (`control_fields_read`). If the orchestrator ever becomes
model-driven it should be given only the flags in the routing view, which already carry everything a
routing decision needs (verdict, round count, escalation condition).

Result (estimated tokens, orchestrator calls only, Phase 1 clean case unless noted):
unbounded view 83 to 223 and rising; bounded (3 handoffs, counts instead of id lists) 78 to 146;
after the loop guard and review loop were added with their data in the view 115 to about 240;
after moving them to the control channel 106 to 174 for a clean run and at most 174 across a
three-round review loop. The figures are identical for 1 and 12 documents (107 vs 106 at the first
call). `test_orchestrator_view_is_bounded` checks that the view does not grow with 500 documents,
a 400-entry log, or 200 messages; `test_orchestrator_view_excludes_deterministic_only_inputs`
checks the split.

Trade-off: the orchestrator cannot see which specific documents are pending. It does not need to; the
extraction fan-out reads the document list from graph state, not from the orchestrator's view.
