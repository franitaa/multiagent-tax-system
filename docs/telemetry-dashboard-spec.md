# Telemetry dashboard: spec

Owner: orchestration (Person 1). Status: proposal, bonus work. Nothing here changes how a case runs.

## What it is for
The volunteer dashboard answers "which case needs a person?". This page answers "is the system behaving?":
where time and tokens go, how often the safety nets fire, and whether anything that should never happen
did. It is for the team and the grader, to show the architecture working (assignment: routing, context
management, guardrails, auditability).

It is **not an agent**. The system still has exactly six agents. It is a read-only page over files the
runner already writes.

## Rules it must follow
- **Read-only.** It never writes to `traces/`, the audit log, the checkpointer, or state. It never calls a
  tool or a model.
- **No new personal data.** Traces hold field names, never values; the audit log holds events and actors,
  never answers or amounts (`src/audit.py`). The page shows only those. No document text, no facts, no
  notes. Case IDs are shown (they are not secrets, but they are not passwords either).
- **No new data collection.** Everything below comes from fields that already exist. If a panel needs a
  new field, that is a separate change to the runner, reviewed on its own.
- **Honest numbers.** Tokens say whether they are `estimate` or real API usage (`token_source`). A missing
  value is shown as missing, never as zero.
- **A bad file does not break the page.** A corrupt or truncated line is skipped and counted ("3 lines
  could not be read").

## Where the data comes from
| Source | Fields used |
|---|---|
| `traces/<thread_id>.jsonl`, one line per agent call | `agent`, `step`, `thread_id`, `ts`, `duration_ms`, `handoff` {from, to, reason}, `fields_read`, `fields_written`, `input_tokens`, `output_tokens`, `token_source`, `context_mode`, `tools_called`, `tool_transports`, `violations`, `error` (only on a clean halt: the error type) |
| `traces/audit/<case_id>.jsonl`, hash-chained | `event` (`escalation_raised`, `paused_for_volunteer`, `volunteer_decision`, `document_flagged`, `draft_ready`, `draft_form_written`, `case_stopped`, `halted_by_error` (added by #36), `viewed`, `case_purged`), `actor`, `ts`, `details` (condition, decision, ...) |
| `AuditLog.verify(case_id)` | the tamper check |

The thread ID and the case ID are the same string for the chat page; where they differ (tests) the page
joins on equality and shows the case without audit data otherwise.

## Panels
1. **Runs.** One row per thread: final outcome (`complete`, `halted_by_human`, `halted_by_error`, still
   waiting), number of agent calls, wall time (first to last `ts`), total input and output tokens.
   Click a row to open its timeline.
2. **Run timeline.** The calls in order: agent, duration, the handoff and its reason, tools used and their
   transport. Shows the hub-and-spoke shape (every agent returns to the orchestrator) and parallel
   extraction.
3. **Agents.** Per agent: calls, average and slowest duration, input and output tokens, share of the
   total. Estimated and real tokens are split. This is the evidence for the context-management decision
   (`docs/decisions/001-context-strategy.md`): input tokens per call stay flat as sessions grow.
4. **Escalations.** Count by condition; how each ended (`continue`, `stop`); how long cases waited for a
   volunteer; which agent raised them. Includes `LOOP_GUARD`, `REVIEW_BOUND_EXCEEDED` and
   `ELIGIBILITY_UNDECIDED`, so the orchestrator's own stops are visible.
5. **Review loop.** Runs where Review sent work back: rounds per run, which check failed (the check name
   only, from the handoff reason), how many ended at the bound.
6. **Safety checks.** Red when non-zero:
   - calls whose `violations` list is not empty (an agent wrote outside its allow-list, or sent a
     malformed update);
   - tax tools called with transport `local` (the tools should run over MCP);
   - `document_flagged` events (possible instructions hidden in a document);
   - `halted_by_error` runs (tool server unreachable).
7. **Audit integrity.** Per case: chain intact or broken, number of entries, last event. A broken chain is
   shown at the top of the page.
8. **Overview.** Cases by outcome, and the share that needed a volunteer. This is the first thing on the
   page.

## Design
- `src/telemetry.py`: plain functions over a trace directory, returning plain dicts and lists (no
  Streamlit, no I/O except reading files). Everything the page shows comes from here, so it is tested
  without a browser.
- `src/ui/telemetry_dashboard.py`: a Streamlit page, drawn only. Same style and accessibility rules as the
  other pages (large text, labels, no colour-only meaning: every red item also says "ALERT"). Runs on its
  own port (`streamlit run src/ui/telemetry_dashboard.py --server.port 8503`) with a "Refresh" button;
  no live tailing.
- Directory taken from `SILVERFILE_TRACE_DIR` (already in `.env.example`), default `traces`.
- No new dependency.

## Tests
Traces are produced by running the real graph on the existing scenarios, so the tests follow the
system as it changes:
- clean run: outcome `complete`, calls in the expected order, token totals add up;
- spouse-died case: one escalation, `continue`, wait time present;
- review loop (text-amount Extraction stand-in): one send-back round;
- tool server down: `halted_by_error` shown, nothing computed;
- loop guard scenario: `LOOP_GUARD` counted;
- a forced violation and a `local` transport are flagged;
- a tampered audit line is reported as a broken chain;
- a corrupt trace line is skipped and counted;
- a guard test that the telemetry module and page import nothing that writes (no `open(..., "w")`, no
  `AuditLog.record`) and never read a value field.

## Build order (three small commits)
1. `src/telemetry.py` with its tests.
2. `src/ui/telemetry_dashboard.py` and a page test (Streamlit `AppTest`, as the other pages do).
3. README line and the `docs/STATUS.md` entry.

## Out of scope
Live tailing, alerts by email, a login, per-taxpayer drill-down into answers or amounts, and changing the
trace format. Whatever the page needs from the runner that does not exist yet is listed here and decided
separately.

## Open questions
1. **Separate page or a tab in the volunteer dashboard (#35)?** Recommendation: separate page. The
   audiences differ (team and grader versus volunteers) and it avoids touching Supriya's files.
2. **Should the page be reachable from the taxpayer app?** Recommendation: no. Staff only, by URL, like
   the volunteer page; it has no login (classroom demo).
