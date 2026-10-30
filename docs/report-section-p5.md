# Report section: Computation, provenance and security (Person 5)

**Draft for the team report (card REP-1).**

## Role
Computation agent, provenance, and the Security focus area: tax-math tools, provenance records,
the draft 1040-SR with click-to-see sources, fake-SSN validation, and PII/document handling.

## Design
Computation never does arithmetic itself. It calls deterministic tools (`tax_math.py`) in a fixed dependency
order, and each call goes over MCP to a tool server (`src/tax_math_mcp.py`, started over stdio by
`src/mcp_client.py`) so no amount is computed in the agent's own process, and every amount it returns is a provenance record: value,
formula, inputs, source and tool. Amounts from documents cite the document; amounts the taxpayer
typed record the field name, date and who entered them (the "direct user input" fallback). The
draft form shows each amount as click-to-expand, so a reviewer can trace any number to its inputs,
and refuses to render an amount without a full record. Line 6b (taxable Social Security) is
computed from the rest of income and then feeds total income and AGI; the senior deduction is
computed from AGI. Redaction and an untrusted-document label are applied at the single runner
boundary that every agent call passes through.

## Failure modes and out-of-scope handling
- Missing filing status: Computation fails loudly instead of guessing.
- Tool server down: the run stops with a clear error. There is no silent fallback to in-process
  arithmetic, because that would hide that the MCP rule is not being met.
- Text amounts from Extraction (`"1000.00"`): the first pass does not use them, Review flags the
  line, and the send-back makes Computation read them (a repaired draft says so in its formula). A
  volunteer's filing-status decision is never replaced by Rules' stale one; Review keeps failing
  until Rules agrees, and the bounded loop then hands the case to a human.
- In-scope income forms Extraction does not read (SSA-1099, 1099-INT, 1099-DIV): the lines they feed
  say "NOT READ" in their source, the draft form warns at the top, and nothing is invented. Amounts the
  taxpayer types for those forms are used as direct-input records and count as read (the proposed
  fact names are in `docs/answer-names.md`, not yet asked by Intake).
- Taxpayer who can be claimed as a dependent, itemizing spouse, 1099-R with box 2b, 1099-NEC and
  similar: Computation stops and escalates to a human instead of calculating.
- Not handled (documented in `docs/provenance.md`): qualified-dividend rates, QCD, dual-status
  aliens, special married-filing-separately Social Security rule.
- Prompt injection: instruction-like document text is flagged and audited, not rewritten. Agents are
  contained by allow-lists and shape checks (a dollar amount cannot exist without provenance), so an
  agent that obeys a document still cannot write outside its fields. A model persuaded to misreport
  a value inside its own fields is caught only by Review and the human gate.
- Audit and retention: each case has a tamper-evident audit log (who decided what, no personal
  data); cases can be deleted on request or expire after 30 idle days, and deleting a case also removes
  the uploads it was read from. Not done: encryption at
  rest, authentication, wiping backups (docs/security.md).
- Redaction is regex-based and can miss unusual formats; it is a defensive filter, not a guarantee.
  Document text is labelled as data, but nothing here can stop a model that is careless with it.
- Tax tables were checked against IRS Rev. Proc. 2024-40; one error (the 12% bracket tops) was
  found and fixed during review.

## Testing
Hand-calculated expected values for each tool including boundary cases, an end-to-end return,
tool-order checks, a graph run showing provenance survives state updates, escalation tests, and
tests that traces, the form and chat messages never show or hold a real-looking SSN, and a check
that fails if the Computation agent does arithmetic itself. Full suite on `p5/issue-41-typed-amounts`
(Windows, Python 3.13, based on `main` at PR #39), Oct 30, 2026: 1203 passing, 3 expected failures
(xfail), and 9 failing tests in the chat page, home page and volunteer dashboard page tests. The same
9 fail on `main` without this work, so they are not caused by it. Earlier, on Oct 28, the count was
835 passing and 2 expected failures, before PR #30 and #33 and this work merged.

## Accessibility and dignity (P5's part)
Unsolicited real-looking SSNs are removed (in the chat page and again where messages enter the
graph state) and the user is told why in plain language; no SSN is
requested for the taxpayer or spouse; the draft form masks dependents' SSNs and uses large type
and keyboard-operable details.

## Contribution
Person 5: provenance schema and helpers, tax-math tools and tests, Computation agent, draft form,
fake-SSN validation, PII redaction, document security, MCP tool server, audit log, case retention,
the unread income-form warning and typed amounts for those forms (issue #27).
