# Report section: Computation, provenance and security (Person 5, Sahana)

**Draft; edit into the final report. Bracketed items are for you to fill in.**

## Role
Computation agent, provenance, and the Security focus area: tax-math tools, provenance records,
the draft 1040-SR with click-to-see sources, fake-SSN validation, and PII/document handling.

## Design
Computation never does arithmetic itself. It calls deterministic tools (`tax_math.py`, also served
over MCP) in a fixed dependency order, and every amount it returns is a provenance record: value,
formula, inputs, source and tool. Amounts from documents cite the document; amounts the taxpayer
typed record the field name, date and who entered them (the "direct user input" fallback). The
draft form shows each amount as click-to-expand, so a reviewer can trace any number to its inputs,
and refuses to render an amount without a full record. Line 6b (taxable Social Security) is
computed from the rest of income and then feeds total income and AGI; the senior deduction is
computed from AGI. Redaction and an untrusted-document label are applied at the single runner
boundary that every agent call passes through.

## Failure modes and out-of-scope handling
- Missing filing status: Computation fails loudly instead of guessing.
- Taxpayer who can be claimed as a dependent, itemizing spouse, 1099-R with box 2b, 1099-NEC and
  similar: Computation stops and escalates to a human instead of calculating.
- Not handled (documented in `docs/provenance.md`): qualified-dividend rates, QCD, dual-status
  aliens, special married-filing-separately Social Security rule.
- Redaction is regex-based and can miss unusual formats; it is a defensive filter, not a guarantee.
  Document text is labelled as data, but nothing here can stop a model that is careless with it.
- Tax tables were checked against IRS Rev. Proc. 2024-40; one error (the 12% bracket tops) was
  found and fixed during review.

## Testing
Hand-calculated expected values for each tool including boundary cases, an end-to-end return,
tool-order checks, a graph run showing provenance survives state updates, escalation tests, and
tests that traces and the form never show real-looking SSNs. [Add: final test count and date.]

## Accessibility and dignity (P5's part)
Unsolicited real-looking SSNs are removed and the user is told why in plain language; no SSN is
requested for the taxpayer or spouse; the draft form masks dependents' SSNs and uses large type
and keyboard-operable details. [Add demo timestamp.]

## Contribution
Sahana: provenance schema and helpers, tax-math tools and tests, Computation agent, draft form,
fake-SSN validation, PII redaction, document security, MCP tool server.
