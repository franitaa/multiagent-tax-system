# Intake to Rules: fact names and value shapes

For Supriya (Intake) and Matthew (Rules). Decision already made: **we use Supriya's Intake, so its fact
names and value shapes are the source of truth (`docs/answer-names.md`). Rules adapts.**
Everything below comes from running the real Intake and the real Rules together in our graph, and
from a pattern search of `src/agents/rules.py`. The name mapping is my reading; please confirm it.

## What happens today
A scripted single filer (born 1950, one W-2) answered all 24 Intake questions. The graph finished
with status `complete`, but Rules returned `filing_status: None`, `eligible_1040sr: None`,
`taxpayer_qualifies: None`, no citations, and still `in_scope: true`. Rules never saw the answers
because it looks for different names. Nothing stopped the run from ending "complete".

## 1. Names: what Rules reads today, and what Intake writes
Only `taxpayer_blind` and `spouse_blind` match.

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

## 4. Open question: finishing with nothing decided
When Rules cannot determine eligibility or filing status, the draft should not end as complete. Two
options, not decided: Rules escalates when it cannot decide, or the orchestrator refuses to finish
while `eligibility.filing_status` is empty. I lean towards both (Rules says why; the orchestrator
guarantees it). Orchestration will not change anything until you choose.

## Done means
These strict expected failures start passing, and the `xfail` markers are removed:
- `tests/test_rules_intake_contract.py::test_rules_finds_the_birth_date_under_intakes_name`
- `tests/test_rules_intake_contract.py::test_a_no_answer_to_blindness_is_not_counted_as_blind`
- `tests/test_e2e_intake.py::test_rules_decides_eligibility_and_status_from_real_intake_facts`
  (runs once Intake is merged)
- `tests/test_scenarios.py::test_the_human_supplied_filing_status_reaches_the_draft`

Run them with `pytest -rxX`; strict mode reports the first one that is fixed as a failure, which is
the signal to delete its marker.
