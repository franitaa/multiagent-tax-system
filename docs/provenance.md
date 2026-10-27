# Computation, provenance and security (Person 5)

Cards covered: PRV-1/2/3, CMP-1/2/3/4, SEC-1/2. Spec: Assignment 7 sections 3.1, 3.2, 4, 4.2.

## Provenance
Every dollar amount in `state["computed"]` is a record with `value`, `formula`, `inputs`,
`source`, `tool` (`provenance.py`).
- Calculated lines come from the tools in `tax_math.py`, called through the Computation agent's
  `ToolBox` (the runner logs each call). **Every call goes over MCP**: `src/mcp_client.py` starts
  the server `python -m src.tax_math_mcp` (stdio) and the ToolBox sends the tool call there, so no
  amount is computed in the agent's own process. Each trace record lists `tool_transports`
  (`mcp`, or `local` for P3's extraction tool). `SILVERFILE_TOOL_TRANSPORT=local` runs the same
  functions in-process, on purpose, for debugging. If the server cannot start the run stops with
  `McpUnavailable`; there is no silent fallback. Review uses the same tools to recompute.
- Amounts read from a document carry `source = "Document <id> (Document Extraction)"`.
- Amounts the taxpayer typed (adjustments, estimated payments, Schedule 1/2/3) are direct-input
  records: `field_name`, `entered_by`, `entered_on` are in `inputs`.
- `src/draft_form.py::render_draft_html(computed, facts, eligibility)` shows the draft form; click
  (or keyboard-activate) any amount to see its record. It refuses to show a line with an
  incomplete record, shows filing status, the 12d box count and dependents, masks dependents'
  SSNs, and shows only valid 900-series test numbers.
- Sample: `python scripts/render_draft.py` writes `demo/sample_1040sr.html`.

## Lines produced (ids follow section 3.1)
1a, 1z, 2a, 2b, 3a, 3b, 4a, 4b, 5a, 5b, 6a, 6b, 9, 10, 11a, 12e, 13b, 14, 15, 16, 17, 18, 20,
22, 23, 24, 25a, 25b, 25d, 26, 31, 33, 34, 37.
Order: documents and direct inputs -> 6b (needs the rest of income) -> 9 -> 11a -> 12e ->
13b (needs AGI) -> 14 -> 15 -> 16 -> 18/22/24 -> 25d -> 33 -> 34 / 37. Line 6b feeds 9 and 11a;
tests assert the call order and the 6b -> 9 link.

## Defensive escalations in Computation (Rules should normally catch these first)
`OUT_OF_SCOPE` if the taxpayer can be claimed as a dependent, a separately filing spouse itemizes
(section 3.2 rule 2: the Standard Deduction Chart does not apply), or a 1099-NEC/MISC/B/K is
present; `FORM_1099R_BOX_2B` if a 1099-R has box 2b checked or no taxable amount. Not raised again
once a human has resolved the condition.

## Security
- `security.py::is_fake_ssn` (900-999 only) is the one SSN rule; Intake uses it, and the draft
  form shows only numbers that pass it.
- The runner redacts non-test SSNs, EINs, emails and phone numbers in document text, labels
  documents `untrusted_document_data`, and redacts handoff reasons written to traces.
- Limits: regex redaction is a defensive filter, not a guarantee. Embedded instructions are
  labelled as data; the Extraction agent must not treat document text as instructions.
  Escalation reasons and human-decision notes written by other agents are not redacted.
- Dual-status aliens (section 3.2 rule 2) are not detected here; Rules/Intake must escalate.

## Known limitations
- Line 16 uses the 2025 ordinary rate schedules only (brackets checked against Rev. Proc.
  2024-40). Qualified-dividend rates (3a) are not applied; the spec says "rate schedule".
- Taxable Social Security uses the spec's thresholds and the standard worksheet. The special
  "lived with spouse, filing separately" rule is not in the spec and is not applied.
- MFS eligibility for the Schedule 1-A senior deduction is not special-cased (not stated in the spec).
- Whole-dollar rounding is not applied; amounts are kept to cents.
- QCD flag on 1099-R (spec 4a/4b) is not handled.

## Review send-backs
Review's findings arrive in `view["pending_revision"]` (`{"target", "round", "findings":
[{"check", "line", "issue"}]}`). Computation re-runs everything and acts on two kinds:
- `check == "sources"` (a document amount did not reach its line): amounts written as text, such as
  `"20000.00"` or `"$20,000.00"`, are read as numbers. The first pass does not read them, so
  Extraction's text amounts reach Review as a failure and the second pass fixes them. The line's
  formula records that the text was read after a review finding.
- `check == "recompute"` and the issue mentions the filing status: the status in `eligibility` is
  used. Never when the status in `facts` is a volunteer's decision (`human:` source): that is not
  Computation's to override, and Review keeps failing until Rules agrees with the volunteer.

Anything else (scope, completeness, contradictions) is not acted on; the loop bound then sends the
case to a human. The handoff reason names what was repaired (`lines computed again after review: ...`).
Computation also uses Rules' `taxpayer_qualifies` / `spouse_qualifies` for the 65+ boxes when
present, which is what Review checks them against.

## Draft form output (PRV-3)
The draft 1040-SR is a standalone HTML page (`src/draft_form.py`). Click an amount, or tab to it and
press Enter, to see its formula, inputs, source and tool; "Show all sources" opens them all and
Print opens every source first. It shows every section 3.1 item: filing status (and whether Rules
or a volunteer set it), each line 12d box (from what the standard-deduction tool was actually given),
dependents (name, relationship, masked test SSN), every computed line, what Review found and how many
send-back rounds it took, and each volunteer decision with the volunteer's name. A line without a full
provenance record is never rendered, and everything from documents or answers is HTML-escaped.

Where it comes from:
- **Chat page:** when a case finishes, [src/ui/taxpayer_chat.py](../src/ui/taxpayer_chat.py) shows the form
  inline with a "Download the draft form" button.
- **Scenarios:** `python -m scripts.run_scenarios clean` (also `spouse-died`, `interrupt`) writes
  `output/<run>_1040sr.html` and prints the path (`--output-dir` to change; the folder is ignored by Git).
- **Any saved case:** `python -m scripts.render_case <case id>` reads the case from
  `runtime/team_checkpoints.sqlite` (the store the chat page and workbench use). The dashboard can call
  `write_draft_form(state, directory, name, audit=...)` or `render_draft_html(...)` directly.
- **Demo files:** `python -m scripts.render_draft` rewrites `demo/sample_1040sr.html` (every income type),
  `demo/eval_case_1_1040sr.html` (clean run) and `demo/eval_case_2_1040sr.html` (volunteer resolves a
  spouse's death, filing status set to married filing jointly).
Writing a form records `draft_form_written` in the audit log.

## Integration notes
- Computation's scoped view keeps numeric facts plus a named list (`COMPUTATION_FACTS` in
  `src/orchestration/context.py`): the volunteer's `filing_status` override, birth dates,
  blindness answers, `can_be_claimed_as_dependent`, `spouse_itemizing`. Without them the
  context strategy silently changed the return (tests/test_computation_scoped_view.py).
- A custom tool registry (P3) is merged over the default one, so Computation keeps its tax tools.
- The form's filing status is the volunteer's override if there is one, else Rules' decision,
  the same order Computation uses.

## Open items for teammates (placeholders; nothing blocks Computation)
- Extraction owner: extracted field names are in `DOC_LINES` at the top of
  `src/agents/computation.py`: W-2 `box_1`/`box_2`; 1099-INT `box_1`/`box_4`/`box_8`; 1099-DIV
  `box_1a`/`box_1b`/`box_4`; 1099-R `box_1`/`box_2a`/`box_2b`/`box_4` and `ira_sep_simple`
  (true = IRA, line 4; otherwise pension, line 5); SSA-1099 `box_5`/`box_6`. P3's W-2 output
  (`box_1`, `box_2`, ... as numbers) matches; the other document types are only exercised by
  our own tests.
- Intake owner: add questions for Schedule 2/3 amounts if wanted (`schedule2_part1_tax`,
  `schedule2_other_taxes`, `schedule3_nonrefundable_credits`, `schedule3_payments`); Computation
  reads them if present.
- Rules owner: `eligibility["age_blindness_boxes"]` is shown on the form if Rules writes it.
- UI/dashboard owner: show `write_draft_form` output (or `render_draft_html(...)`) on the results
  page and the dashboard.
- Review owner: recompute totals from `computed` with the same tools; check 6b <= 6a.
