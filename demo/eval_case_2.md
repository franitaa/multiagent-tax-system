# Eval case 2: a human-in-the-loop event, resolved

The taxpayer's husband died during 2025. Whether she files as married filing jointly, qualifying
surviving spouse or single is a filing-status ambiguity, so SilverFile does not guess: the chat
pauses (a LangGraph interrupt) and a volunteer decides on the dashboard. The interview then carries
on, the W-2 photo is checked, and the draft is finished with the volunteer's filing status.

## The data (fictional)
| What | Value |
|---|---|
| Taxpayer | Pat Tester, born March 4, 1950, widowed during 2025, not blind, no dependents |
| Document | W-2 photo [`data/fixtures/w2_02.jpg`](../data/fixtures/w2_02.jpg) |
| W-2 box 1 / box 2 | $31,234.00 / $2,087.00 ([`expected.json`](../data/fixtures/expected.json)) |
| Volunteer's decision | Married filing jointly: a spouse who died during the year still counts as married for that year |

## Before you start
As in eval case 1: `cp .env.example .env` with **your own** OpenAI or Anthropic key (read once, when
the app starts), then `docker compose up --build` (or `streamlit run src/ui/silverfile_home.py`) and
open http://localhost:8501.

## Steps
**A. The taxpayer** (**I'm a taxpayer** → **Start or continue my questions** → **Start a new session**;
note the case ID)

Answer as in eval case 1, with these differences (`#` is the order in this interview, **Q** the number in
[`docs/intake-script.md`](../docs/intake-script.md)):

| # | Q | Question (short) | Answer |
|---|---|---|---|
| 2 | Q1 | Married on December 31, 2025? | `no` |
| 3 | Q3 | Single, widowed, or taking care of someone? | **`widowed`** |
| 8 | Q13 | Did you get a W-2 form? | `yes` → tick **I confirm this is not a real tax form.**, choose **`w2_02.jpg`**, **Add my W-2** |
| 22 | Q22 | **Did a spouse pass away during 2025?** | **`yes`** |

Q3a (*"In what year did your husband or wife pass away?"*) is not asked: it is only for a widowed
taxpayer with dependents.

**B. Pause 1: the filing status.** After `yes` to question 22 the chat says a volunteer will help. The
case waits as `FILING_STATUS_AMBIGUITY` (raised by Intake).

On the dashboard (**I'm a Kushim volunteer** → **Open the volunteer dashboard**, type your name):
1. Open the case: *"The filing status is unclear (for example, a spouse died during the year)."*
2. **Your decision:** **Continue: the taxpayer carries on**.
3. **If you continue: the correct filing status:** **Married filing jointly**.
4. **Note for the record** (required), e.g. "Spouse died in 2025; a joint return is allowed for that
   year." → **Save decision**.

Continuing without a note, or without a filing status, is refused, and the same question stays.

**C. The taxpayer again.** Back in the chat (same case ID; **Check again** if it is still waiting),
answer the last questions: *lived in the US for all of 2025?* → `yes`, *answering yourself?* → `yes`.

**D. Pause 2: the W-2 check.** The photo is read and the case waits as `EXTRACTION_REVIEW`. On the
dashboard, open the case, compare the photo with box 1 **31234.00** and box 2 **2087.00**, choose
**Accept**, tax year **2025**, tick **I compared the amounts with the photo, and this is a W-2.**, add a
note, **Save decision**. After the volunteer's filing status, Rules runs again with it.

**E. The draft.** The chat shows **Your draft tax form**.

## What you should see on the draft
| Line | Amount | Where it comes from |
|---|---|---|
| Filing status | **Married filing jointly** | the volunteer's decision (`human:FILING_STATUS_AMBIGUITY`) |
| 12d | 1 box (taxpayer 65 or older) | Rules |
| 1a / 1z wages | $31,234.00 | W-2 box 1 |
| 12e standard deduction | $33,100 | $31,500 + $1,600 (joint return) |
| 13b senior deduction | $6,000 | one qualifying person |
| 15 taxable income / 16 tax | $0 / $0 | 31,234 is below the deductions |
| **34 refund** | **$2,087.00** | all of the W-2 withholding (box 2) |

The case history on the dashboard shows both decisions, with the volunteer's name and note.

To stop instead (e.g. the volunteer needs to see the death certificate first): choose **Stop the case**.
The case ends as `halted_by_human` and the chat says a volunteer will be in touch.

## The automatic check
`python -m evals.runner --case eval-case-2-spouse-died --case eval-case-2-status-reaches-draft` runs
the same decision without the browser: the pause, the volunteer's `married_filing_jointly` with a
note, Rules running again, and the draft finished with that filing status. CI runs it on every push.

The same case from the command line: `python -m scripts.run_scenarios spouse-died`.

## Not covered
The deceased spouse's age is not asked, so only the taxpayer's 65+ box is counted. If the spouse was
also 65 or older, a joint return would have a second box ($34,700); a volunteer would note it.
