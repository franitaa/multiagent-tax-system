# Shared answer names (`facts`)

Owner: Supriya Patil (Intake). Agreed with Francesca (orchestration). Changes to this list
need a heads-up in the team chat first, like the rest of the shared state.

## Summary (read this first)
**What this file is:** the names Intake uses to save the taxpayer's answers in
`state["facts"]`, and what each one can contain. Rules, Computation, Review and the
dashboard should read answers using exactly these names.

**The one rule about filing status ("claim vs confirmed"):**
1. **Intake records plain answers only** (married on Dec 31? one return together? widowed?).
   Working out the filing status is a tax rule, so Intake never writes a filing status.
   The placeholder's `filing_status_claim` is **not used** by the real Intake.
2. **Rules decides** the filing status and writes it to `eligibility["filing_status"]`.
3. **A volunteer can override it** through the human gate. That is saved as
   `facts["filing_status"]` with source `"human:FILING_STATUS_AMBIGUITY"`. If it exists,
   Rules should use it instead of its own decision.

**What is still open:** nothing blocking. New names are added here first.

---

## Format of every answer
Each answer is saved as `facts[name] = {"value": ..., "source": ...}`.

| `source` | Meaning |
|---|---|
| `"user"` | The taxpayer typed it in the chat. |
| `"direct user input"` | An amount the taxpayer typed (also has `entered_by` and `entered_on`), as the brief allows for values we do not compute. |
| `"human:<CONDITION>"` | A volunteer's decision from the human gate (e.g. `"human:FILING_STATUS_AMBIGUITY"`). |
| `"intake"` | Intake's own bookkeeping, not an answer. |

`"not_sure"` is a valid value for almost every question: it means the taxpayer did not know,
and the question is listed in `volunteer_notes` for a volunteer to follow up.

If the taxpayer changes an answer, the earlier one is kept in `history`; nothing is deleted.
If a change means a question no longer applies (e.g. "married" becomes "not married"), the
old answer is kept: **only use an answer if its question applies.**

## Answer names
| Name | Question (short) | Value |
|---|---|---|
| `taxpayer_name` | Your full name | text |
| `married_dec31` | Married on December 31, 2025? | `"yes"` / `"no"` / `"not_sure"` |
| `file_jointly` | One return together with your spouse? (married only) | `"yes"` / `"no"` / `"not_sure"` |
| `spouse_name` | Spouse's full name (joint return only) | text |
| `spouse_itemizing` | Will your spouse itemize on their own return? (married, filing separately) | `"yes"` / `"no"` / `"not_sure"` |
| `household_situation` | Single, widowed, or caring for someone? (not married) | `"single"` / `"widowed"` / `"caring_for_someone"` / `"not_sure"` |
| `taxpayer_birth_date` | Your date of birth (read back and confirmed before saving) | `"YYYY-MM-DD"` / `"not_sure"` |
| `taxpayer_blind` | Are you legally blind? | `"yes"` / `"no"` / `"not_sure"` |
| `spouse_birth_date` | Spouse's date of birth (married only, confirmed) | `"YYYY-MM-DD"` / `"not_sure"` |
| `spouse_blind` | Is your spouse legally blind? (married only) | `"yes"` / `"no"` / `"not_sure"` |
| `has_dependents` | Does anyone depend on you? | `"yes"` / `"no"` / `"not_sure"` |
| `dependents` | Each dependent | list of `{"name", "relationship", "ssn"}`; `ssn` is a test number 900-999 only |
| `dependents_complete` | Nobody else depends on you | `"yes"` |
| `spouse_death_year` | Year the spouse died (widowed with dependents only) | a number, e.g. `2023`, or `"not_sure"` |
| `has_w2`, `has_ssa_1099`, `has_1099_r`, `has_1099_int`, `has_1099_div` | Which in-scope documents they have | `"yes"` / `"no"` / `"not_sure"` |
| `has_other_tax_forms` | Any other forms (1099-NEC, 1099-MISC, 1099-B)? | `"yes"` / `"no"` / `"not_sure"` |
| `sold_stocks_or_property` | Sold stocks, funds or property in 2025? | `"yes"` / `"no"` / `"not_sure"` |
| `business_or_rental_income` | Business, freelance or rental income? | `"yes"` / `"no"` / `"not_sure"` |
| `foreign_income_or_accounts` | Income, accounts or investments outside the US? | `"yes"` / `"no"` / `"not_sure"` |
| `digital_assets` | Received, sold or traded digital assets? | `"yes"` / `"no"` / `"not_sure"` |
| `made_estimated_payments` | Sent tax payments to the IRS themselves? | `"yes"` / `"no"` / `"not_sure"` |
| `estimated_payments_amount` | How much in total | number, source `"direct user input"` |
| `has_adjustments` | Any adjustments to income? | `"yes"` / `"no"` / `"not_sure"` |
| `adjustments_amount` | Total adjustments (Schedule 1, line 26) | number, source `"direct user input"` |
| `refund_method` | Refund by bank account or paper check? | `"bank_account"` / `"paper_check"` / `"not_sure"` |
| `refund_account_own_name` | Is that account in your own name? | `"yes"` / `"no"` / `"not_sure"` |
| `can_be_claimed_as_dependent` | Can someone claim you as a dependent? | `"yes"` / `"no"` / `"not_sure"` |
| `spouse_can_be_claimed` | Can someone claim your spouse? (married only) | `"yes"` / `"no"` / `"not_sure"` |
| `spouse_died_2025` | Did a spouse pass away during 2025? | `"yes"` / `"no"` |
| `us_resident_all_year` | Lived in the US for all of 2025? | `"yes"` / `"no"` / `"not_sure"` |
| `answering_for_self` | Answering these questions yourself? | `"yes"` / `"no"` |
| `helper_description` | Who is helping, and are they allowed to act for you? | text |

**Never asked, on purpose:** the taxpayer's or spouse's SSN (the brief only requires
dependents' SSNs, and says not to ask for SSNs we do not need) and bank account numbers.

## For Rules (Matthew): Intake records these, Rules decides what they mean
Intake never judges scope or tax rules. Please decide these in Rules and raise
`OUT_OF_SCOPE` (or another condition) where needed:
`has_other_tax_forms`, `sold_stocks_or_property`, `business_or_rental_income`,
`foreign_income_or_accounts`, `digital_assets`, `can_be_claimed_as_dependent`,
`spouse_can_be_claimed`, `spouse_itemizing`, `us_resident_all_year`, `spouse_death_year`.

Intake does raise these itself, because it is the only agent that hears the taxpayer:
`TAX_ADVICE_REQUEST`, `FILING_STATUS_AMBIGUITY` (spouse died in 2025), and
`EXPLOITATION_SIGNS` (someone else answering without permission, pressure, or a refund
account not in the taxpayer's name).

## Amounts for the forms Extraction does not read (issue #27, step 2)
Agreed by Computation (Sahana) and Intake (Supriya); asked by Intake right after "yes" to the form (questions Q14a-b,
Q16a-c and Q17f-h in `docs/intake-script.md`). Each is a number, source `"direct user input"`, and is
read by Computation (`TYPED_AMOUNTS` in `src/income_forms.py`). Once a form has one of these, it counts
as read.

| Name | Box on the form | Line it feeds | Question |
|---|---|---|---|
| `ssa1099_benefits` | SSA-1099 box 5, net benefits | 6a | Q14a |
| `ssa1099_withheld` | SSA-1099 box 6, federal tax withheld | 25b | Q14b |
| `int1099_taxable` | 1099-INT box 1, interest income | 2b | Q16a |
| `int1099_tax_exempt` | 1099-INT box 8, tax-exempt interest | 2a | Q16b |
| `int1099_withheld` | 1099-INT box 4, federal tax withheld | 25b | Q16c |
| `div1099_ordinary` | 1099-DIV box 1a, total ordinary dividends | 3b | Q17f |
| `div1099_qualified` | 1099-DIV box 1b, qualified dividends | 3a | Q17g |
| `div1099_withheld` | 1099-DIV box 4, federal tax withheld | 25b | Q17h |

Limit: one typed amount marks its form as read. So Intake asks the other boxes of a form (withholding,
tax-exempt interest, qualified dividends) only once the form's main amount (box 5, box 1 or box 1a)
is a number: if the taxpayer is not sure of it, nothing is typed for that form and the case pauses for a
volunteer (`INCOME_NOT_READ`) instead of finishing without that income.

If a form was also read from an uploaded document, the document wins and the typed amount for that form is
not added (it would count twice); the line's source says so. Review checks a typed amount against the answer
in `facts`, including when it is summed with others (the input is labelled `facts.<name>`).

## Not answers (other agents can ignore these)
| Name | Meaning |
|---|---|
| `volunteer_notes` | Questions a volunteer should look at: `{"question", "question_text", "reason", "resolved"}` (plus `taxpayer_words` for safety notes, with any real-looking SSN removed). |
| `intake_progress` | Intake's bookkeeping: which question it is asking, the order of answers, and a date being confirmed. |
| `filing_status` | Only ever written by the human gate (a volunteer's decision); see the rule at the top. |
