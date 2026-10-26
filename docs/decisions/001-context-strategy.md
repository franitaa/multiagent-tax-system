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

Result (estimated tokens, orchestrator calls only, clean case): Phase 1 unbounded view 83 to 223 and
rising; after bounding, 78 to 146 and flat once the 3-handoff window is full. Later phases added
the loop guard's fingerprint history (8 hex chars each, capped at 24) and, only while a failed
review is being routed, its findings. Current figures: 115 to about 203 for a clean run, up to about
240 across a three-round review loop. Both are bounded by constants (3 handoffs, 24 fingerprints),
and a run with 12 documents gives exactly the same numbers as one with 1 document.
`test_orchestrator_view_is_bounded` checks that the view does not grow with 500 documents, a
400-entry log, or 200 messages.

Trade-off: the orchestrator cannot see which specific documents are pending. It does not need to; the
extraction fan-out reads the document list from graph state, not from the orchestrator's view.
