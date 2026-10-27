# Intake to Rules: fact names and value shapes

For Supriya (Intake) and Matthew (Rules). Decision already made: **we use Supriya's Intake, so its fact
names and value shapes are the source of truth (`docs/answer-names.md`). Rules adapts.**
Everything below comes from running the real Intake and the real Rules together in our graph, and
from a pattern search of `src/agents/rules.py`.

> **Status: the name mapping in section 1 is UNCONFIRMED.** It is my reading, not an agreement.
> It stays marked unconfirmed until Matthew (Rules) and Supriya (Intake) have both confirmed it.
> **The reference for what Intake writes is Supriya's shared list of answer names,
> [`docs/answer-names.md`](answer-names.md)** (merged to `main` in #8). If that list and this table
> disagree, the list wins, and this table should be corrected.

## What happens today
(The orchestrator now pauses instead of finishing; see section 4.) A scripted single filer (born 1950, one W-2) answered all 24 Intake questions. The graph finished
with status `complete`, but Rules returned `filing_status: None`, `eligible_1040sr: None`,
`taxpayer_qualifies: None`, no citations, and still `in_scope: true`. Rules never saw the answers
because it looks for different names. At the time, nothing stopped the run from ending "complete";
now the orchestrator pauses with `ELIGIBILITY_UNDECIDED` (section 4).

## 1. Names: what Rules reads today, and what Intake writes (UNCONFIRMED)
Only `taxpayer_blind` and `spouse_blind` match. The right-hand column is **my unconfirmed guess**;
check each row against [`docs/answer-names.md`](answer-names.md) before acting on it.

| Rules reads | Intake writes (likely equivalent) | Note |
|---|---|---|
| `taxpayer_dob`, `age` | `taxpayer_birth_date` | ISO string, e.g. `"1950-03-04"` |
| `spouse_dob`, `spouse_age` | `spouse_birth_date` | same |
| `spouse_died_during_tax_year` | `spouse_died_2025`, `spouse_death_year` | `"yes"`/`"no"` |
| `taxpayer_can_be_claimed_as_dependent` | `can_be_claimed_as_dependent` | |
| `spouse_itemizes` | `spouse_itemizing` | |
| `filing_status_claim` | none | Intake never writes a filing status. Rules derives it from `married_dec31`, `file_jointly`, `household_situation`, `spouse_died_2025` |
| `dual_status_alien` | `us_resident_all_year` | meaning is inverted and broader; please check |
| `tax_advice_requested`, `financial_exploitation_flag`, `document_user_conflict`, `has_1099r_taxable_amount_not_determined`, `filing_status_ambiguous` | none | See section 3 |

A volunteer's answer at the human gate is stored as `facts["filing_status"]` with source
`human:FILING_STATUS_AMBIGUITY`. If it exists, Rules must use it instead of deriving a status
(`tests/test_scenarios.py` already tracks this).

## 2. Value shapes: Intake writes strings, not booleans
Intake stores `"yes"`, `"no"` and `"not_sure"` as strings. Rules currently runs `bool(...)` on them,
and `bool("no")` is `True`. Tested directly:

| `taxpayer_blind` | age/blindness boxes (born 1950) |
|---|---|
| `False` | 1 (correct) |
| `"no"` | **2 (wrong: a "no" counted as blind)** |
| `"yes"` | 2 |

Renaming facts does not fix this: it needs a small parser for yes/no/not_sure, and a decision for
`"not_sure"` (ask again, or escalate; it must not silently become yes or no). It affects every
yes/no fact Rules reads.

## 3. Flags: use `escalation`, not facts
Rules reads several flag-like facts that the real Intake does not write. The real Intake raises
conditions itself: a spouse who died raised `FILING_STATUS_AMBIGUITY` through the human gate in our
test. Rules should (a) not depend on those flag facts for anything Intake escalates, (b) check
`human_decisions` before raising a condition again, and (c) keep only the conditions it can detect
itself (for example a conflict between a document and an answer, or a 1099-R with box 2b checked from
extracted data), raising them as `escalation`.

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

## 5. Out-of-scope screening: nobody escalates it yet
Business rule 5: only the in-scope profile is handled; everything else goes to a human. Intake asks the
screening questions (Q17a-e, plus Q21 and Q23) but, **by design, only records the answers**
(`docs/intake-script.md`: "Rules decides"). Rules does not read those facts:

| Intake records (answer `"yes"` or `"not_sure"` means out of scope or unclear) | Rules reads it? |
|---|---|
| `sold_stocks_or_property` | no |
| `business_or_rental_income` | no |
| `foreign_income_or_accounts` | no |
| `digital_assets` | no |
| `has_other_tax_forms` | no |
| `can_be_claimed_as_dependent`, `us_resident_all_year` | not under these names |

So today a taxpayer who says they have crypto, a business and foreign accounts is not turned away: the
run pauses as `ELIGIBILITY_UNDECIDED` (for the wrong reason), and once Rules can read Intake's names it
would **complete** unless it also handles these. **Owner: Matthew (Rules).** For each screening fact,
`"yes"` (and, your call, `"not_sure"`) should raise `OUT_OF_SCOPE` with a reason that names the item.
Status of this section: the fact list above is from running the real Intake; whether `not_sure` should
escalate or be re-asked is a decision for Matthew and Supriya.

## Done means
These strict expected failures start passing, and the `xfail` markers are removed:
- `tests/test_rules_intake_contract.py::test_rules_finds_the_birth_date_under_intakes_name`
- `tests/test_rules_intake_contract.py::test_a_no_answer_to_blindness_is_not_counted_as_blind`
- `tests/test_e2e_intake.py::test_rules_decides_eligibility_and_status_from_real_intake_facts`
  (runs once Intake is merged)
- `tests/test_scenarios.py::test_the_human_supplied_filing_status_reaches_the_draft`
- `tests/test_e2e_intake.py::test_an_out_of_scope_screening_answer_escalates_as_out_of_scope` (5 cases)

Already guaranteed by orchestration, whatever Rules does: a run never ends "complete" without a filing
status (`tests/test_eligibility_invariant.py`).

Run them with `pytest -rxX`; strict mode reports the first one that is fixed as a failure, which is
the signal to delete its marker.
