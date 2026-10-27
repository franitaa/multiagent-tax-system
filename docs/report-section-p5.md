# Report section: Computation, provenance and security (Person 5)

**Draft; edit into the final report. Fill in the bracketed items yourself.**

## Design
Computation never does arithmetic itself. It calls deterministic tools (`tax_math.py`) in a fixed
dependency order, and every amount it returns is a provenance record: value, formula, inputs,
source and tool. Amounts from documents cite the document; amounts the taxpayer typed record the
field name, date and who entered them. The draft form shows each amount as click-to-expand, so a
reviewer can trace any number back to its inputs. Redaction and an untrusted-document label are
applied at the single runner boundary that every agent call passes through.

## Failure modes and limits
- Missing filing status: Computation fails loudly instead of guessing.
- Tax situations the tools do not special-case (see `docs/provenance.md`, Known limitations) must be
  escalated by Rules, not computed.
- Redaction is regex-based and can miss unusual formats; it is a defensive filter only.
- Document text is labelled as data, but nothing here can stop a model that is careless with it.

## Testing
Hand-calculated expected values for each tool, an end-to-end return, tool-order checks, a graph run
showing provenance survives state updates, and tests that traces contain no real-looking SSNs.
[Add: final test count and date from your last run.]

## Accessibility and dignity (P5's part)
Unsolicited real-looking SSNs are removed and the user is told why in plain language; no SSN is
requested for the taxpayer or spouse. [Add demo timestamp.]

## Contribution
[Your name]: provenance schema and helpers, tax-math tools and tests, Computation agent, draft
form, fake-SSN validation, PII redaction, document security. [Edit as you see fit.]
