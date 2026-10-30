# 2025 Form 1040-SR — Eligibility and Rules Policy Corpus

**Project:** SilverFile multi-agent tax system  
**Tax year:** 2025 only  
**Purpose:** Reference corpus for the Rules Agent and machine-verifiable citations for Review.  
**Citation format:** `policy.md §2.1` (use the numbered heading exactly as written).  

## 1.1 Source hierarchy and interpretation

This file summarizes the tax-year-2025 rules specified in Assignment 7 and cross-references public IRS instructions. If a project simplification differs from actual tax law, explicitly flag the limitation and escalate rather than inventing a rule. Rules decides eligibility, applicable checks and scope; deterministic computation calculates dollar amounts. The citation identifies the section of this file that supports each Rules decision.

**Primary project source:** Assignment 7, *Implement a multi agent tax system*, specification §§3.1–3.3 and agent responsibilities in §4.  
**IRS references:** [2025 Form 1040/1040-SR instructions](https://www.irs.gov/instructions/i1040gi), [2025 Form 1040-SR including Standard Deduction Chart](https://www.irs.gov/pub/irs-pdf/f1040s.pdf), [2025 Publication 554](https://www.irs.gov/publications/p554), [2025 Publication 915](https://www.irs.gov/publications/p915), [IRS senior-deduction overview](https://www.irs.gov/newsroom/working-families-tax-cuts-individuals-and-workers).

## 2.1 Form 1040-SR eligibility

For tax year 2025, Form 1040-SR is available when the taxpayer was born **before January 2, 1961**. On a married-filing-jointly (MFJ) return, at least one spouse needs to satisfy the age requirement. The project specification imposes no income restriction on using Form 1040-SR. A missing, invalid or uncertain date of birth must not be represented as a confirmed eligibility verdict.

**References:** Assignment 7 §3.2, Rule 1; IRS 2025 Instructions for Forms 1040 and 1040-SR, “What form to file.”

## 2.2 Filing status and volunteer override

The supported filing statuses are single, married filing jointly, married filing separately, head of household, and qualifying surviving spouse. Intake captures marital and household answers; Rules determines or validates the filing status. In particular, `caring_for_someone` alone does not prove eligibility for head-of-household status, and `widowed` alone does not prove qualifying-surviving-spouse status. Escalate ambiguous cases for human review rather than guessing.

A filing status explicitly supplied by the human gate under `facts["filing_status"]`, with the source `human:FILING_STATUS_AMBIGUITY`, takes precedence over a new deduction from older Intake answers. Rules may use the short codes (`mfj`, `mfs`, `hoh`, `qss`) internally, but always writes the full names that Computation expects (`single`, `married_filing_jointly`, `married_filing_separately`, `head_of_household`, `qualifying_surviving_spouse`) to `eligibility["filing_status"]`.

**References:** Assignment 7 §§3.1 and 4; team `docs/answer-names.md` and Intake–Rules contract.

## 2.3 Age and blindness boxes — Form 1040-SR line 12d

Count one box for each qualifying and **confirmed** condition: taxpayer age 65 or older, taxpayer blind, eligible spouse age 65 or older, and eligible spouse blind. The taxpayer is treated as at least age 65 for tax year 2025 when born before January 2, 1961. Only an affirmative `"yes"` confirms blindness; `"no"` does not add a box. `"not_sure"` does **not** add a blindness box, but known age boxes must still be counted, and the blindness uncertainty must be resolved before the deduction is finalized.

**Caution:** For married filing separately, the 2025 Form 1040-SR chart restricts when spouse boxes may be checked. Do not assume that all spouse age/blindness boxes qualify merely because filing status is `mfs`.

**References:** Assignment 7 §3.2, Rule 2; 2025 Form 1040-SR Standard Deduction Chart and its footnotes, page 4; IRS Topic 551.

## 2.4 Standard deduction chart and exceptions

For tax year 2025 the base standard deductions in the assignment are: Single/MFS **$15,750**; MFJ/QSS **$31,500**; HOH **$23,625**. Each confirmed age/blindness box adds **$2,000** if unmarried and not a surviving spouse, otherwise **$1,600**, subject to the actual chart and filing-status restrictions. Rules reports the box count and applicability; Computation performs the dollar calculation with the project's deterministic tools.

Do not use the ordinary 1040-SR Standard Deduction Chart without additional review when someone can claim the taxpayer or an applicable spouse as a dependent, when a separately filing spouse itemizes, or when the taxpayer is a dual-status alien. These conditions are escalation points in the assignment.

**Not implemented yet:** the dual-status alien case. Rules escalates the first two (the `can_be_claimed_as_dependent` / `spouse_can_be_claimed` and `spouse_itemizing` answers), but Intake does not ask about dual status, so Rules cannot detect it and the chart is applied. This is a known limitation.

**References:** Assignment 7 §3.2, Rule 2; 2025 Form 1040-SR Standard Deduction Chart, page 4.

## 2.5 Schedule 1-A enhanced senior deduction

This is a **separate deduction** from the age/blindness standard-deduction boxes. For 2025–2028, an otherwise eligible individual age 65 or older may claim up to **$6,000** (up to **$12,000** for two eligible spouses on a joint return), with a 6% phaseout for modified adjusted gross income above **$75,000** or **$150,000** for joint filers. The actual IRS rules also impose a valid-SSN requirement and require married taxpayers to file jointly for this deduction. Rules should only mark this deduction applicable after checking relevant requirements; Computation calculates any allowable amount.

**References:** Assignment 7 §3.2, Rule 3; 2025 Instructions for Forms 1040/1040-SR (Schedule 1-A); IRS “Working Families Tax Cuts — Individuals and Workers.”

## 2.6 Taxable Social Security benefits

If an SSA-1099 is present, the tax return may need the taxable Social Security worksheet. The calculation depends on other income, tax-exempt interest, and one-half of benefits; commonly used base amounts are **$25,000** for single/HOH/QSS and **$32,000** for MFJ, with second-tier amounts of **$34,000** and **$44,000**, respectively. Married-filing-separately treatment has additional rules depending on living arrangements; do not assume the regular thresholds always apply. Rules flags the worksheet's applicability, while Computation handles the ordering and arithmetic.

**References:** Assignment 7 §3.2, Rule 4; IRS Publication 915 (2025), Worksheet A and taxable benefits worksheets.

## 3.1 Supported tax scope and unsupported situations

The assignment's supported document types are W-2, SSA-1099, 1099-R, 1099-INT and 1099-DIV; it supports standard deduction, Schedule 1-A senior deduction and specified direct-entry amounts from Schedules 1, 2 and 3. Unsupported cases are escalated for human review rather than computed: itemized Schedule A deductions; business/freelance or nonemployee income needing Schedule C; rental Schedule E; capital gains needing Schedule D; digital assets; foreign income/accounts; amended or prior-year returns; and state tax returns.

`"not_sure"` in a scope-screening answer should not be silently treated as a known `"no"` or confirmed `"yes"`. Apply the project's human/clarification contract and record the precise uncertainty.

**References:** Assignment 7 §3.3 Scope; project Intake–Rules answer names.

## 3.2 Form 1099-R Box 2b exception

If Box 2b indicates that the taxable amount was not determined, the assignment requires a human escalation. Deriving the taxable portion using the Simplified Method or General Rule is outside the implemented computation scope. Do not complete the supported computation path for this case without an authorized resolution.

**References:** Assignment 7 §3.3 Scope (1099-R exception).

## 3.3 Uncertain blindness and human review

When a relevant taxpayer or spouse blindness answer is `"not_sure"`, retain any **confirmed age boxes** from §2.3 but do not count an unconfirmed blindness box. Record why the answer is uncertain, request the human-review pathway recognized by the orchestrator, and do not finalize the deduction until the human decision is integrated. The existence of a `handoff_request` alone does not prove that the orchestrator paused; integration tests must verify the gate.

**References:** §2.3 above; project team's Intake/Rules/Human routing agreement.

## 3.4 Form 1099-NEC screening

Form 1099-NEC reports nonemployee compensation and is outside
this assignment's supported income/document scope.

If Extraction identifies an uploaded Form 1099-NEC,
Rules must mark the case out of scope and raise OUT_OF_SCOPE,
even when Intake did not report other tax forms.

**References:** Assignment 7 §3.3 Scope;
§3.1 above.

## 3.5 Uploaded in-scope documents versus Intake answers

Rules compares the presence of each uploaded **supported** document (W-2, SSA-1099,
1099-R, 1099-INT, 1099-DIV) with the corresponding Intake answer (`has_w2`,
`has_ssa_1099`, `has_1099_r`, `has_1099_int`, `has_1099_div`). If Intake explicitly
recorded `"no"` but an uploaded document of that type is present, Rules must flag
`SOURCE_CONFLICT` and identify the disputed fact for human resolution before
computation. A missing answer or `"not_sure"` is not, by itself, a contradiction.
A volunteer can supply `{fact_name: corrected_value}`; the orchestrator records it
in `facts` with source `human:SOURCE_CONFLICT`; eligibility is then cleared and Rules
re-runs its eligibility and scope checks with the corrected answer before the draft can
finish. After a volunteer has continued, Rules does not raise the same conflict again.

A conflict depends only on the uploaded document's kind, not on whether Extraction read
its amounts. If the corrected form has no amounts (Extraction does not yet read SSA-1099,
1099-INT or 1099-DIV), the case may pause again for `INCOME_NOT_READ` until the taxpayer
types the amounts (see `docs/answer-names.md`).

**References:** Assignment 7 §4 (eligibility rules and human escalation);
project `docs/answer-names.md` and the team handoff contract.

## 4.1 Human decisions and Review send-back

Rules should honor a supported, resolved human decision and not endlessly re-escalate the same condition. Human-supplied factual corrections must be available in `facts` in the agreed `{"value": ..., "source": ...}` shape. Review may send a finding back through `pending_revision` when supported by state permissions and orchestration. Rules must inspect that finding, correct unsupported or missing citations by reference to this corpus, and only proceed if eligibility/scope decisions are supportable. Do not manufacture facts merely to satisfy Review.

**References:** Assignment 7 §4 (Rules, Review/Audit and orchestrator responsibilities); shared application contracts.

## 4.2 Citation contract for Review

Every applied Rules decision must have a citation to an existing numbered section in this file. Each pair should be machine-readable, for example:

```json
{"rule": "1040-SR eligibility", "citation": "policy.md §2.1"}
```
**References:** Assignment 7 §4 (Eligibility & Rules must cite); agreed Rules–Review interface.
