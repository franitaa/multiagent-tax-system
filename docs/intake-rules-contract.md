# Intake to Rules: fact names and value shapes

For Supriya (Intake) and Matthew (Rules). Decision already made: **we use Supriya's Intake, so its fact
names and value shapes are the source of truth (`docs/answer-names.md`). Rules adapts.**
Everything below comes from running the real Intake and the real Rules together in our graph, and
from a pattern search of `src/agents/rules.py`.

> **Status (2026-10-30): CONFIRMED by Matthew (Rules)** against the current `src/agents/rules.py`.
> Supriya (Intake): confirmation pending, to be given on the pull request for this change.
> **The reference for what Intake writes is Supriya's shared list of answer names,
> [`docs/answer-names.md`](answer-names.md)** (merged to `main` in #8). If that list and this table
> disagree, the list wins, and this table should be corrected.

## What happened before Rules was fixed (history)
(The orchestrator now pauses instead of finishing; see section 4.) A scripted single filer (born 1950, one W-2) answered all 24 Intake questions. The graph finished
with status `complete`, but Rules returned `filing_status: None`, `eligible_1040sr: None`,
`taxpayer_qualifies: None`, no citations, and still `in_scope: true`. Rules never saw the answers
because it looks for different names. At the time, nothing stopped the run from ending "complete";
now the orchestrator pauses with `ELIGIBILITY_UNDECIDED` (section 4).

## 1. Names: what Intake writes, and what Rules does with it (CONFIRMED)
Rules now reads Intake's names directly (`_fact_value()` / `_fact_source()` on the `{"value", "source"}`
records). Rules only receives the facts listed in `RULES_FACTS` (`src/orchestration/context.py`): if Rules
starts reading a new fact, add it there too, or `tests/test_context_views.py` fails.

| Intake fact | What Rules does with it | Where in `rules.py` |
|---|---|---|
| `taxpayer_birth_date`, `spouse_birth_date` | 1040-SR eligibility (born before 1961-01-02) and the age boxes | `_qualifies_for_1040sr`, `run` |
| `married_dec31`, `file_jointly`, `household_situation` | Derives the filing status | `_derive_filing_status` |
| `spouse_death_year` | Widowed branch; a widowed status goes to a volunteer | `_derive_filing_status` |
| `filing_status` (source `human:FILING_STATUS_AMBIGUITY` only) | The volunteer's decision, used instead of deriving a status | `_human_filing_status_override` |
| `taxpayer_blind`, `spouse_blind` | Blindness boxes; `not_sure` raises `ANSWER_UNCERTAIN` | `run` |
| `has_other_tax_forms`, `sold_stocks_or_property`, `business_or_rental_income`, `foreign_income_or_accounts`, `digital_assets`, `can_be_claimed_as_dependent`, `us_resident_all_year` | Out-of-scope screening | `screening_checks` in `run` |
| `spouse_can_be_claimed` (married), `spouse_itemizing` (separate return) | Out-of-scope screening for the spouse | `run` |
| `has_w2`, `has_ssa_1099`, `has_1099_r`, `has_1099_int`, `has_1099_div` | **Planned:** compared with uploaded documents to raise `SOURCE_CONFLICT` (#41); to be added to `RULES_FACTS` | to add |

Legacy names still accepted only for old test fixtures, never preferred: `filing_status_claim`, `age`, `spouse_age`.
Old Rules names no longer used: `taxpayer_dob`, `spouse_dob`, `spouse_died_during_tax_year`,
`taxpayer_can_be_claimed_as_dependent`, `spouse_itemizes`, `dual_status_alien` and the flag facts
(`tax_advice_requested`, `financial_exploitation_flag`, `document_user_conflict`,
`has_1099r_taxable_amount_not_determined`, `filing_status_ambiguous`; see section 3).

**Intake facts Rules does not read, on purpose:** `taxpayer_name`, `spouse_name`, `has_dependents`,
`dependents`, `dependents_complete` (not needed by any in-scope rule); `spouse_died_2025` (Intake raises
`FILING_STATUS_AMBIGUITY` itself); `made_estimated_payments`, `estimated_payments_amount`,
`has_adjustments`, `adjustments_amount` (amounts for Computation); `refund_method`,
`refund_account_own_name`, `answering_for_self`, `helper_description` (Intake's safety checks).

A volunteer's answer at the human gate is stored as `facts["filing_status"]` with source
`human:FILING_STATUS_AMBIGUITY`. If it exists, Rules must use it instead of deriving a status
(`tests/test_scenarios.py` already tracks this).

## 2. Value shapes: Intake writes strings, not booleans
Intake stores `"yes"`, `"no"` and `"not_sure"` as strings. Rules never calls `bool()` on an answer
(`bool("no")` is `True`); it uses `_normalize`, `_is_yes`, `_is_no`, `_is_not_sure` and
`_is_valid_yes_no_not_sure`. An invalid answer goes back to Intake. A `"no"` blindness answer no longer
counts as blind (the old bug is in the history section above).

How `"not_sure"` is handled (it never silently becomes yes or no):

| Answer | Rules |
|---|---|
| `married_dec31`, `file_jointly`, `household_situation`, `taxpayer_blind`, `spouse_blind`, and every screening question (section 5) | `ANSWER_UNCERTAIN` for that one fact |
| `taxpayer_birth_date` | Back to Intake for a follow-up |

## 3. Flags: use `escalation`, not facts
Rules no longer reads flag facts. The real Intake raises `TAX_ADVICE_REQUEST`, `FILING_STATUS_AMBIGUITY`
(spouse died in 2025) and `EXPLOITATION_SIGNS` itself; Rules keeps an escalation that is already pending
(`_preserve_pending_escalation`) and does not raise a condition again once a volunteer resolved it with
"continue" (`_resolved_conditions`, from `human_decisions`).

Rules raises only the conditions it can detect itself:
- `OUT_OF_SCOPE`: not 1040-SR eligible, a screening answer, or an extracted 1099-NEC document.
- `FORM_1099R_BOX_2B`: an extracted 1099-R with box 2b checked.
- `FILING_STATUS_AMBIGUITY`: possible Head of Household, widowed, or another status it cannot prove.
- `ANSWER_UNCERTAIN`: one `not_sure` answer it needs (section 2).
- `SOURCE_CONFLICT` (**planned**, #41): a `has_*` answer is `"no"` but that form was uploaded.

## 4. Finishing with nothing decided: decided, built in orchestration
**Decision (team):** the orchestrator must not finish with an empty filing status or eligibility
verdict. It now pauses for a human with the condition `ELIGIBILITY_UNDECIDED` (raised by the
orchestrator, **stop-only**) when the result from Rules has no `filing_status`, no boolean `in_scope`,
or an `eligible_1040sr` of `None`. The reason names exactly what is missing. The check runs right after
Rules (nothing is computed on an undecided status) and again before a case could end "complete".
Out of scope still wins, and `eligible_1040sr: False` is a verdict, not a gap.

**What this asks of Rules:** always return a non-empty `filing_status` and a boolean `in_scope`; use
`eligible_1040sr: None` only to mean "I could not decide". Rules should still raise its own specific
escalation when it can say why (that is a better message than the generic one).

## 5. Out-of-scope screening: Rules escalates it
Business rule 5: only the in-scope profile is handled; everything else goes to a human. Intake asks the
screening questions (Q17a-e, plus Q21 and Q23) but, **by design, only records the answers**
(`docs/intake-script.md`: "Rules decides"). Rules reads them all:

| Intake records (answer `"yes"` or `"not_sure"` means out of scope or unclear) | Rules reads it? |
|---|---|
| `sold_stocks_or_property` | yes |
| `business_or_rental_income` | yes |
| `foreign_income_or_accounts` | yes |
| `digital_assets` | yes |
| `has_other_tax_forms` | yes |
| `can_be_claimed_as_dependent` | yes (answer `"yes"` is out of scope) |
| `us_resident_all_year` | yes (answer `"no"` is out of scope) |
| `spouse_can_be_claimed`, `spouse_itemizing` | yes, when they apply (married / separate return) |

Rules also screens extracted documents: a 1099-NEC is out of scope even if Intake missed it.

**Status:** Rules now raises `OUT_OF_SCOPE` for a `"yes"` screening answer, with a reason that names the item
(`tests/test_e2e_intake.py::test_an_out_of_scope_screening_answer_escalates_as_out_of_scope`, 5 cases), and
an unsure answer is not continued past (eval `sold-property-not-sure`). **Decision (Matthew and Supriya, 2026-10-30; Supriya's request on #49): a `not_sure` screening answer raises `ANSWER_UNCERTAIN`, naming the fact, not `OUT_OF_SCOPE`.** The volunteer asks the taxpayer and answers yes or no (`UNCERTAIN_ANSWERS` in `human.py`): "no" lets the case continue, "yes" ends it as `OUT_OF_SCOPE`. A definite out-of-scope answer is checked first, so no one is asked about an unsure answer on a case that stops anyway (`tests/test_uncertain_screening.py`). Intake does not re-ask. The fact list above is from running the real Intake.

## Done means (all of these pass on `main`; the markers are gone)
These were strict expected failures. They pass now, and the `xfail` markers are removed:
- `tests/test_rules_intake_contract.py::test_rules_finds_the_birth_date_under_intakes_name`
- `tests/test_rules_intake_contract.py::test_a_no_answer_to_blindness_is_not_counted_as_blind`
- `tests/test_e2e_intake.py::test_rules_decides_eligibility_and_status_from_real_intake_facts`
- `tests/test_scenarios.py::test_the_human_supplied_filing_status_reaches_the_draft`
- `tests/test_rules.py::test_extracted_1099nec_must_not_pass_supported_scope_screening`
- `tests/test_e2e_intake.py::test_an_out_of_scope_screening_answer_escalates_as_out_of_scope` (5 cases)

Already guaranteed by orchestration, whatever Rules does: a run never ends "complete" without a filing
status (`tests/test_eligibility_invariant.py`), and after a volunteer's answer the gate clears `eligibility`
so Rules decides again (`tests/test_status_reruns_rules.py`, `tests/test_answer_uncertain.py`).

Rules' view of `facts` is now an allow-list of the answers it reads (`RULES_FACTS` in
`src/orchestration/context.py`): it no longer receives names, dependents or volunteer notes. If Rules starts
reading a new fact, add it there; the guard test fails until you do.

Run them with `pytest -rxX`; strict mode reports the first one that is fixed as a failure, which is
the signal to delete its marker.
