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
| Intake | `messages` (**last 6 only**), `facts` (all), `session_summary` | `messages`, `facts`, `pending_question`, `intake_complete` |
| Extraction | `documents` (one per worker) | `extracted` (keyed by `doc_id`); tool `p3_extract_w2` |
| Rules | `facts` (**only the answers Rules reads**, `RULES_FACTS` in `context.py`: no names, dependents or volunteer notes), `extracted`, `session_summary` | `eligibility`(including `rule_citations`) |
| Computation | `facts` (**numeric values only**), `extracted`, `eligibility` (**`filing_status` only**), `pending_revision` | `computed` (line -> ProvenanceRecord) |
| Review | `computed`, `eligibility`(including `rule_citations`), `facts` (**numeric values only**), `extracted`, `session_summary` | `review` (`{verdict: "pass"\|"fail", findings, send_back_to}`); never fixes anything. Tools: the four `tax_math` tools, to recompute |
| Human gate | `case_id`, `extracted` | `human_decisions`, `status`, `done`, `facts`, `extracted`, `eligibility`; tool `p3_verify_w2` (orchestrator-owned, not an agent) |

### Labels for form lines and documents
Taxpayer answers are named in `docs/answer-names.md`. This adds the two labels it does not
cover, following the names the skeleton already uses. Review (`src/agents/review.py`) checks
against them and sends work back that does not follow them.
- **Form lines:** `computed` keys are `line_<n>` as on the 1040-SR: `line_1a`, `line_6b`,
  `line_11a` (AGI), `line_12e` (standard deduction), `line_13b` (senior deduction), `line_25d`, ...
- **Document boxes:** `extracted[doc_id] = {"kind": "W-2", "fields": {"box_1": {"value": ...}}}`.
  A provenance input taken from a document is keyed `"<doc_id>.<box>"` (`"w2-1.box_1"`); one
  taken from another line is keyed by that line (`"line_9"`).
- **Tool lines:** 6b, 12e, 13b and 16 come from the `tax_math` tool of the same name in `TOOLS`.
- **Typed-in amounts:** as in `docs/answer-names.md`: `source: "direct user input"` plus
  `entered_by` and `entered_on`.

### What Review checks
Review (`src/agents/review.py`) tries to falsify the assembled return. It never fixes anything: it
returns findings `{check, line, issue, severity}` and either passes, sends the work back to
Computation, or escalates.
- Checks: `provenance` (every line has a full record), `sources` (cited document amounts match
  `extracted`; every in-scope document amount reaches its line), `recompute` (lines 6b, 12e, 13b and 16
  re-run through the same `tax_math` tools), `totals`, `contradictions`, `completeness`, `scope`.
- Errors fail the review (`send_back_to: "computation"`, bounded by the review loop below). Warnings
  never fail it. A scope problem also raises `OUT_OF_SCOPE` (Rules said out of scope or not eligible
  for the 1040-SR, an out-of-scope document or a Schedule A/C/D/E line) or `FORM_1099R_BOX_2B`.
- Review does its own arithmetic on purpose: the no-arithmetic rule binds Computation, whose numbers
  are the ones under test.
- Known gap (#27): a document Extraction skipped (`status: "skipped"`, no fields) has no amounts to
  compare, so Review passes it. The orchestrator pauses the case for it before Computation
  (`INCOME_NOT_READ`, below), and Computation and the draft form flag it too.

### Documents Extraction does not read
Extraction reads W-2s only. For anything else it still writes a record, so nothing disappears:
- SSA-1099, 1099-INT and 1099-DIV (in scope, not read yet): `{"kind", "fields": {}, "status":
  "skipped", "reason"}` and a handoff to Rules. Their amounts never reach the draft (issue #27). The
  lines they feed say `NOT READ` in their provenance source (Computation) and the draft form shows an
  "Income is missing from this draft" warning (`src/income_forms.py`). The amount stays zero. The case
  pauses once for a volunteer (`INCOME_NOT_READ`) before Computation, and goes on only if the volunteer
  continues with a note. The same pause covers a W-2 or 1099-R the taxpayer said they have (`has_w2`,
  `has_1099_r`) but never uploaded: without it that case finished with wages of $0. A W-2's amounts come
  only from the uploaded image: there is no typed-wages fact, so typing wages does not clear the pause
  (the three unread forms can be cleared by typed amounts once Intake asks them, #27 step 2).
- 1099-R: escalates `FORM_1099R_BOX_2B` (box 2b cannot be read; a volunteer checks it).
- Any other kind: escalates `OUT_OF_SCOPE`.
- A W-2 whose reading needs a visual check: escalates `EXTRACTION_REVIEW` (below).

### Rules policy citations

The Rules Agent writes the applied tax rules and their supporting references as paired
records in **`eligibility["rule_citations"]`**, using numbered sections of `docs/policy.md`.
This is part of `eligibility`, **not** a separate top-level state field.

```python
{
    "eligibility": {
        "rule_citations": [
            {"rule": "1040-SR eligibility", "citation": "policy.md §2.1"},
            {"rule": "Standard deduction age/blindness rule", "citation": "policy.md §2.3"},
        ]
    }
}
```

- Every recorded applied rule must have its own `rule` (rule name) and `citation`
  (a real section of `docs/policy.md`).
- Do not add duplicate rule/citation pairs. An empty list is valid if no policy
  rule has been applied yet (for example, an early incomplete-input return).
- The Review Agent is meant to check `eligibility["rule_citations"]` against `docs/policy.md` and report
  missing, invalid, or nonexistent references as findings. **Not built yet**: Review does not read
  the citations today.
- Dollar-amount provenance (`ProvenanceRecord`) is a separate requirement and
  is **not** replaced by policy citations.

**Your view is narrower than the table suggests, on purpose** (`docs/decisions/001-context-strategy.md`):
- **Intake's chat window is not memory.** You see only the last 6 messages. Anything you must remember
  (an early statement, a correction, a worry about pressure) has to be written to `facts` the turn you
  hear it. `facts` is all you get of older turns.
- `session_summary` is a one-line, orchestrator-built list of milestones and human decisions. It never
  contains amounts or chat text; do not rely on it for values.
- Need a field you are not shown? Change `POLICY`/`TRANSFORMS` by PR (tag Person 1); do not work around it.
- Whole-state mode for comparison: `--no-context-strategy` / `build_graph(context_strategy=False)`.

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
`FILING_STATUS_AMBIGUITY`, `EXPLOITATION_SIGNS`, `ANSWER_UNCERTAIN` and `EXTRACTION_REVIEW` (constants in `src/state.py`). The orchestrator
adds `LOOP_GUARD`, `REVIEW_BOUND_EXCEEDED`, `ELIGIBILITY_UNDECIDED` and `INCOME_NOT_READ` itself.
When a flag is pending the orchestrator routes to the `human` node, which calls `interrupt()`
and pauses the thread. The call returns `result["__interrupt__"][0].value` =
`{case_id, condition, reason, raised_by, options, note_required_for_continue, resolution_fields,
also_pending}` (plus `error` if the previous answer was rejected).
A volunteer answers on the same `thread_id` with
`graph.invoke(Command(resume={"decision": ..., "note": ..., "resolution": {...}, "reviewer": "<name>"}), config)`
(`reviewer` is optional; it names the volunteer in `human_decisions` and the audit log)
(the value must be a dict; `Command(resume=None)` crashes inside LangGraph).

| Condition | Allowed decisions |
|---|---|
| `OUT_OF_SCOPE`, `FORM_1099R_BOX_2B`, `EXPLOITATION_SIGNS` | `stop` only (a human cannot take responsibility for work the system must not attempt) |
| `LOOP_GUARD`, `REVIEW_BOUND_EXCEEDED`, `ELIGIBILITY_UNDECIDED` (raised by the orchestrator) | `stop` only |
| `INCOME_NOT_READ` (raised by the orchestrator, after Rules and before Computation, once per form) | `continue` (a note saying how the missing income was handled; **no resolution**; it does not add the amount, the draft keeps $0 for that form) or `stop` |
| `SOURCE_CONFLICT`, `FILING_STATUS_AMBIGUITY`, `TAX_ADVICE_REQUEST` | `continue` or `stop` |
| `ANSWER_UNCERTAIN` | `continue` (with a valid corrected fact) or `stop` |
| `EXTRACTION_REVIEW` (raised by Extraction) | `continue` (an accepted review of that document) or `stop` (rejects the reading) |

- `continue` **requires a non-empty `note`**; it is stored in `human_decisions` (the audit record).
- `continue` may carry a `resolution` (for `FILING_STATUS_AMBIGUITY` it is **required**; a bare `continue` is refused): `FILING_STATUS_AMBIGUITY` takes `{"filing_status": <single |
  married_filing_jointly | married_filing_separately | head_of_household | qualifying_surviving_spouse>}`;
  `SOURCE_CONFLICT` takes `{fact_name: value}`;
  `ANSWER_UNCERTAIN` takes `{fact_name: corrected_value}` for the specific unresolved
  answer (valid values are defined in `docs/answer-names.md`). The resolution is written to `facts` as
  `{"value": ..., "source": "human:<CONDITION>"}`, so read it from `facts` like any other fact.
  `TAX_ADVICE_REQUEST` takes none: put the question in the note for the volunteer.
  `EXTRACTION_REVIEW` takes `{"document_id": <the document in the payload>, "review": {"action": "accept", ...}}`;
  the gate checks the review with the `p3_verify_w2` tool and writes the verified record to `extracted`
  (not to `facts`). Details: `docs/P3_INTEGRATION.md`.
  **Rules must honor it:** if `facts["filing_status"]` exists (source `human:...`), use it instead of
  deriving a status. The gate clears `eligibility` on `continue` for `FILING_STATUS_AMBIGUITY` and
  `ANSWER_UNCERTAIN`, so the router runs Rules again with the new fact (without this the case stopped
  again as `ELIGIBILITY_UNDECIDED`; `tests/test_status_reruns_rules.py`).
- `stop` ends the case with `status == "halted_by_human"`; the note is optional.
- A call ends with one of: `awaiting_user` (Intake asked a question), `awaiting_human` (interrupt),
  `complete` (draft ready, nothing filed), `halted_by_human`, or `halted_by_error` (see Tools).
- An invalid answer does not raise: the call returns another interrupt whose payload has an `error`
  string. Show it and let the volunteer answer again.
- UI rule: while a thread is interrupted, show the taxpayer a neutral waiting message (not the
  reason) and accept no new messages until it is resumed.

**Do not raise a condition again once a human resolved it.** Check `human_decisions` (every agent can
read it): if an entry with your condition exists, carry on. If Rules returns
`eligibility.in_scope == False` without a flag, the orchestrator raises `OUT_OF_SCOPE` itself.

## What Rules must return
A non-empty `eligibility["filing_status"]` and a boolean `eligibility["in_scope"]`. If you also report
`eligible_1040sr`, `None` means "could not decide". If either is missing the orchestrator will not go on
to Computation: it pauses for a human with `ELIGIBILITY_UNDECIDED` (stop-only) and the case cannot end
"complete". Details and the Intake fact names: `docs/intake-rules-contract.md`.

### Rules output

For a taxpayer aged 75 with `taxpayer_blind="not_sure"`, the result must retain
the confirmed age box, leave the unconfirmed blindness box uncounted, and raise a
real escalation. An abbreviated example follows:

```python
{
    "eligibility": {
        "age_blindness_boxes": 1,
        "rule_citations": [
            {"rule": "Standard deduction age/blindness rule", "citation": "policy.md §2.3"},
            {"rule": "Uncertain blindness: human review", "citation": "policy.md §3.3"},
        ],
    },
    "escalation": {
        "pending": True,
        "condition": "ANSWER_UNCERTAIN",
        "reason": "taxpayer_blind is not_sure; volunteer clarification required",
        "raised_by": "rules",
        "fact": "taxpayer_blind",  # the one unresolved answer; the gate asks for exactly this fact
    },
    "handoff_request": {"to": "human", "reason": "ANSWER_UNCERTAIN"},
}
```

The real agent must return its full agreed `eligibility` structure, not just the
abbreviated fields above. As described in **Handoff request**, a handoff alone
cannot guarantee that the orchestrator pauses; the pending escalation is required.

### Volunteer resolution and resume

- `ANSWER_UNCERTAIN` allows `continue` or `stop`, as listed in the decision table.
- `continue` requires a non-empty note **and** `resolution` with exactly one key, the
  `fact` named in the escalation, for example `{"taxpayer_blind": "yes"}` or
  `{"married_dec31": "no"}`. The gate accepts `yes`/`no` for `taxpayer_blind`, `spouse_blind`,
  `married_dec31` and `file_jointly`, and `single`/`widowed`/`caring_for_someone` for
  `household_situation` (`docs/answer-names.md`). `not_sure`, a bool, another fact, or extra
  facts are rejected: the gate interrupts again with an `error` and nothing is applied. The
  interrupt payload lists the fact in `resolution_fields`.
- The human gate validates the resolution, updates the relevant `facts` record,
  and records provenance as `"source": "human:ANSWER_UNCERTAIN"`:

  ```python
  facts["taxpayer_blind"] = {
      "value": "yes",
      "source": "human:ANSWER_UNCERTAIN",
  }
  ```

- On `continue` the gate also clears `eligibility` (the router only runs Rules when there
  is none), so Rules runs again with the corrected fact and recomputes eligibility,
  filing status, and age/blindness boxes as appropriate. Confirmed age boxes stay
  counted while blindness is unknown; an additional blindness box is counted
  only for a confirmed `"yes"` answer.
- A `continue` decision without a valid replacement value cannot bypass the original
  `"not_sure"`: the gate rejects it and the case stays with the volunteer (tested in
  `tests/test_answer_uncertain.py`, including the 1-vs-2-box outcome for blindness).
- Filing-status questions that need human judgment for reasons other than an
  explicit applicable `"not_sure"` still use `FILING_STATUS_AMBIGUITY`.

## Tools and how they run
- Call tools only with `tools.call(name, **kwargs)`; the allow-list is `tools` in `POLICY` (`access.py`).
- Computation and Review use the six/four `tax_math` tools. They run over MCP (`src/mcp_client.py`,
  `src/tax_math_mcp.py`), in a separate process. Extraction's `p3_extract_w2` runs in the agent's own
  process. Every trace record lists `tool_transports` (`mcp` or `local`); a `local` transport for a
  tax tool is a red flag (it happens only with `SILVERFILE_TOOL_TRANSPORT=local`, for tests).
- If the tax-tool server cannot be reached, the run **stops cleanly**: `status == "halted_by_error"`,
  `done == True`, nothing computed or filed. The trace records the error type only (never the message,
  which can hold paths), and the audit log gets a `halted_by_error` entry. Do not catch
  `McpUnavailable` in an agent; do not fall back to computing locally.
- Real model calls: record their actual usage; the runner then logs real token counts
  (`token_source`) instead of the estimate.

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
1. Edit only `src/agents/<your_agent>.py`. Keep `run(view, tools) -> dict`. Do not rename the module or touch `src/agents/__init__.py`. (All six agents are real now except the default Intake: `AGENTS["intake"]` is still the stub, so scenario tests do not start a 24-question interview. `live_agents()` gives the set with the real Intake; the chat page uses it.)
2. Read only from `view`; write only the fields in your table row. If you need another field, open a PR that changes `POLICY` in `access.py` and `SilverState` in `state.py`, and tag Person 1. Do not work around it.
3. Register deterministic tools in `TOOLS` (`access.py`) and add their names to your agent's `tools` in `POLICY`.
4. Return your handoff request and, when a trigger applies, the escalation flag.
5. Tests: no network or model calls in tests. `tests/test_clean_run.py` must still pass with your agent in place. Use `build_graph(trace_dir=tmp_path)` for your own tests.
6. When you call a real model, record its `usage_metadata` in the runner instead of the estimate (`src/orchestration/tokens.py`); coordinate with Person 1.
