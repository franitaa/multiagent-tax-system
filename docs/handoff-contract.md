# Agent contract: state, handoffs, escalation

Read this before changing anything under `src/agents/`. The source of truth is
`src/state.py` (fields) and `src/orchestration/access.py` (allow-lists). Questions or
changes to either go to Person 1 (orchestration).

## The rules
- Agents never call each other. Each agent is `run(view, tools) -> dict` in `src/agents/<name>.py`.
- `view` is a dict holding **only** the fields you may read (below). Anything else does not exist for you.
- Return a **partial update** containing only fields you may write. Writing anything else raises `AccessViolation`.
- Do not log, print or write traces. The runner (`src/orchestration/runner.py`) records every call.
- Tools: only through `tools.call("name", **kwargs)`, and only names on your allow-list.
- Any dollar amount you return must carry a `ProvenanceRecord` (`provenance.py`).

## Who reads and writes what
Every agent can also read `escalation` and `human_decisions`, and write `escalation` and `handoff_request`.

| Agent | Reads | Writes |
|---|---|---|
| Orchestrator | compact routing view (flags, counts; no documents or chat) | control fields only (`next_agent`, `status`, `step`, `handoff_log`, ...) |
| Intake | `messages`, `facts`, `session_summary` | `messages`, `facts`, `pending_question`, `intake_complete` |
| Extraction | `documents` | `extracted` (keyed by `doc_id`) |
| Rules | `facts`, `extracted`, `session_summary` | `eligibility` |
| Computation | `facts`, `extracted`, `eligibility`, `pending_revision` | `computed` (line -> ProvenanceRecord) |
| Review | `computed`, `eligibility`, `session_summary` | `review` (`{verdict: "pass"\|"fail", findings, send_back_to}`); never fixes anything |

## Handoff request
Return `"handoff_request": {"to": "<next>", "reason": "<short text>"}`. `to` is one of
`intake, extraction, rules, computation, review, human, end`; allowed pairs are in
`ALLOWED_HANDOFFS` (`src/state.py`). It is **advisory**: the orchestrator checks it, routes by
state, and logs `honored: true/false` in `handoff_log`. The runner stamps `from`; you cannot
forge it. Keep `reason` free of personal data (it is written to traces).

## Intake: waiting for the taxpayer
One graph call per user message, same `thread_id` (so a Streamlit app calls `graph.invoke(...)`
once per message and never blocks). To ask a question, return:

```python
{"messages": [{"role": "assistant", "content": q}],
 "pending_question": q,
 "handoff_request": {"to": "end", "reason": "awaiting user reply"}}
```

The orchestrator then ends the call with `status == "awaiting_user"`. The UI shows
`result["pending_question"]`. The user's reply is sent as
`graph.invoke({"messages": [{"role": "user", "content": text}]}, config)`; the orchestrator clears
`pending_question` and calls Intake again, which now sees the reply in `messages`. When intake is
finished, return `"intake_complete": True` (and `"pending_question": None`).
Interrupts are **not** used for this; they are reserved for human escalation.

## Escalation (route to a human)
Set a flag; do not stop or work around it. The orchestrator performs the interrupt.

```python
{"escalation": {"pending": True, "condition": "FILING_STATUS_AMBIGUITY",
                "reason": "spouse died in 2025", "raised_by": "intake"}}
```

Conditions: `OUT_OF_SCOPE`, `SOURCE_CONFLICT`, `FORM_1099R_BOX_2B`, `TAX_ADVICE_REQUEST`,
`FILING_STATUS_AMBIGUITY`, `EXPLOITATION_SIGNS` (constants in `src/state.py`). The orchestrator
adds `LOOP_GUARD` and `REVIEW_BOUND_EXCEEDED` itself.
When a flag is pending the orchestrator routes to the `human` node, which calls `interrupt()`
and pauses the thread. The call returns `result["__interrupt__"][0].value` =
`{case_id, condition, reason, raised_by, options, note_required_for_continue, resolution_fields,
also_pending}` (plus `error` if the previous answer was rejected).
A volunteer answers on the same `thread_id` with
`graph.invoke(Command(resume={"decision": ..., "note": ..., "resolution": {...}}), config)`
(the value must be a dict; `Command(resume=None)` crashes inside LangGraph).

| Condition | Allowed decisions |
|---|---|
| `OUT_OF_SCOPE`, `FORM_1099R_BOX_2B`, `EXPLOITATION_SIGNS` | `stop` only (a human cannot take responsibility for work the system must not attempt) |
| `LOOP_GUARD`, `REVIEW_BOUND_EXCEEDED` (raised by the orchestrator) | `stop` only |
| `SOURCE_CONFLICT`, `FILING_STATUS_AMBIGUITY`, `TAX_ADVICE_REQUEST` | `continue` or `stop` |

- `continue` **requires a non-empty `note`**; it is stored in `human_decisions` (the audit record).
- `continue` may carry a `resolution`: `FILING_STATUS_AMBIGUITY` takes `{"filing_status": <single |
  married_filing_jointly | married_filing_separately | head_of_household | qualifying_surviving_spouse>}`;
  `SOURCE_CONFLICT` takes `{fact_name: value}`. It is written to `facts` as
  `{"value": ..., "source": "human:<CONDITION>"}`, so read it from `facts` like any other fact.
  `TAX_ADVICE_REQUEST` takes none: put the question in the note for the volunteer.
- `stop` ends the case with `status == "halted_by_human"`; the note is optional.
- An invalid answer does not raise: the call returns another interrupt whose payload has an `error`
  string. Show it and let the volunteer answer again.
- UI rule: while a thread is interrupted, show the taxpayer a neutral waiting message (not the
  reason) and accept no new messages until it is resumed.

**Do not raise a condition again once a human resolved it.** Check `human_decisions` (every agent can
read it): if an entry with your condition exists, carry on. If Rules returns
`eligibility.in_scope == False` without a flag, the orchestrator raises `OUT_OF_SCOPE` itself.

## Parallelism, the review loop, and the loop guard
- **Extraction runs in parallel**, one worker per document, each receiving exactly one document
  (`view["documents"]` has one entry). Return `extracted` containing only that document's record,
  keyed by its id. Do not read or depend on other documents; results are merged by `doc_id`,
  independent of finishing order. Parallel workers may each set `escalation`; none is lost (the most
  severe is shown first, the rest are queued and shown in turn: `also_pending` lists the conditions
  still waiting in the payload, and each decision records `also_raised` in `human_decisions`. If the
  human stops the case, the queued conditions are recorded there and not shown separately).
- **Review loop.** Review returns `review = {"verdict": "pass" | "fail", "findings": [...],
  "send_back_to": "computation"}`; any other verdict is an error. On `fail` the orchestrator clears
  the old verdict, counts a round, and sends the work to **Computation** (the only supported target
  for now; a request for `rules` or anything else is routed to Computation anyway and logged in
  `review_history` as `requested` vs `sent_to`). Computation then sees `pending_revision = {"target", "round", "findings"}` in its view and
  must address those findings. Review runs again from scratch. At most `max_revisions` rounds (input
  field, default 3); after that the orchestrator raises `REVIEW_BOUND_EXCEEDED` (stop-only).
- **Loop guard.** If an agent's output changes nothing the router looks at (for example `{}`), or the
  same agent is dispatched more than 3 times in a row, the orchestrator raises `LOOP_GUARD`
  (stop-only). So always make progress: set your output fields, or escalate.

## Replacing a stub with a real agent
1. Edit only `src/agents/<your_agent>.py`. Keep `run(view, tools) -> dict`. Do not rename the module or touch `src/agents/__init__.py`.
2. Read only from `view`; write only the fields in your table row. If you need another field, open a PR that changes `POLICY` in `access.py` and `SilverState` in `state.py`, and tag Person 1. Do not work around it.
3. Register deterministic tools in `TOOLS` (`access.py`) and add their names to your agent's `tools` in `POLICY`.
4. Return your handoff request and, when a trigger applies, the escalation flag.
5. Tests: no network or model calls in tests. `tests/test_clean_run.py` must still pass with your agent in place. Use `build_graph(trace_dir=tmp_path)` for your own tests.
6. When you call a real model, record its `usage_metadata` in the runner instead of the estimate (`src/orchestration/tokens.py`); coordinate with Person 1.
