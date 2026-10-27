# Computation, provenance and security (Person 5)

## Provenance
Every dollar amount in `state["computed"]` is a record with `value`, `formula`, `inputs`,
`source`, `tool` (`provenance.py`).
- Calculated lines come from the tools in `tax_math.py`, called through the Computation agent's
  `ToolBox` (the runner logs each call).
- Amounts read from a document carry `source = "Document <id> (Document Extraction)"`.
- Amounts the taxpayer typed (adjustments, estimated payments, Schedule 1/2/3) are direct-input
  records: `field_name`, `entered_by`, `entered_on` are in `inputs`.
- `src/draft_form.py::render_draft_html(computed)` shows the draft form; click an amount to see its
  record. It refuses to show a line with an incomplete record.
- Demo: `python scripts/render_draft.py` writes `draft_1040sr.html`.

## Dependency order (src/agents/computation.py)
documents/direct inputs -> 6b taxable Social Security -> 9 total income -> 11 AGI -> 12e standard
deduction -> 13b senior deduction (uses AGI) -> 14 -> 15 taxable income -> 16 tax -> 18, 22, 24
total tax -> 33 total payments -> 34 refund / 37 amount owed.

## Security
- `security.py::is_fake_ssn` (900-999 only) is the one SSN rule; Intake uses it.
- The runner redacts non-test SSNs, EINs, emails and phone numbers in document text, labels
  documents `untrusted_document_data`, and redacts handoff reasons written to traces.
- Limits: regex redaction is a defensive filter, not a guarantee. Embedded instructions are
  labelled as data; the Extraction agent must not treat document text as instructions.
  Escalation reasons and human-decision notes written by other agents are not redacted.

## Known limitations (tax rules not verifiable from the repo)
- MFS: senior deduction eligibility, $0 Social Security base amount if lived with spouse, and
  spouse age/blindness additions are not special-cased.
- Filers who can be claimed as a dependent: different standard deduction, not handled.
- 1099-R: all of box 2a goes to line 4b (IRA); pensions (5b) only from direct user input.
- Qualified dividends/capital gain rates are not applied (ordinary brackets only).

## Open items for teammates (placeholders; nothing blocks Computation)
- TODO(Rules owner): write `eligibility["filing_status"]` from the real Intake answers
  (`docs/answer-names.md`). Then delete `_intake_status` in `src/agents/computation.py`.
  Also decide the MFS and dependent cases above and escalate or flag them.
- TODO(Extraction owner): confirm extracted field names. Computation assumes W-2 `box_1`/`box_2`,
  SSA-1099 `box_5`, 1099-INT `box_1`/`box_4`/`box_8`, 1099-DIV `box_1a`/`box_4`,
  1099-R `box_2a`/`box_4` (table `DOC_LINES` at the top of `src/agents/computation.py`).
- TODO(Intake owner): confirm `adjustments_amount` and `estimated_payments_amount` are the final
  names, and add questions for Schedule 2/3 amounts and pensions if wanted
  (`schedule2_part1_tax`, `schedule2_other_taxes`, `schedule3_nonrefundable_credits`,
  `schedule3_payments`, `pensions_taxable`).
- TODO(UI owner): show `render_draft_html(result["computed"])` on the results/dashboard page.
- TODO(Review owner): review should read `computed` records and recompute with the same tools.
