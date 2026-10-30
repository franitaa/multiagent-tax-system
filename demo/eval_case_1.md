# Eval case 1: clean minimal run

A single filer born in 1950 with one W-2 and nothing out of scope. The taxpayer answers the
questions in the chat and adds a photo of the W-2; a volunteer checks the amounts read from the
photo; the system produces a draft 1040-SR with the source of every amount. Nothing is filed.

## The data (fictional)
| What | Value |
|---|---|
| Taxpayer | Pat Tester, born March 4, 1950, single, not blind, no dependents |
| Document | W-2 photo [`data/fixtures/w2_01.jpg`](../data/fixtures/w2_01.jpg) |
| W-2 box 1 (wages) / box 2 (federal tax withheld) | $30,000.00 / $2,000.00 ([`expected.json`](../data/fixtures/expected.json)) |
| Everything else | "no" (no other forms, no out-of-scope income, no estimated payments) |

## Before you start
1. `cp .env.example .env` and put **your own** OpenAI or Anthropic key in `.env`. It is only used to
   read the W-2 photo, and it is read once, when the app starts, so fill it in first.
2. Start the app, either way:
   ```
   docker compose up --build                     # then open http://localhost:8501
   streamlit run src/ui/silverfile_home.py       # or locally, in the project's .venv
   ```

## Steps
**A. The taxpayer** (http://localhost:8501 → **I'm a taxpayer** → **Start or continue my questions**)
1. Click **Start a new session**. Note the case ID shown at the top (e.g. `SF-482-735`).
2. Answer each question in **Type your answer here**, then **Send my answer**:

   | # | Question (short) | Answer |
   |---|---|---|
   | 1 | Your full name | `Pat Tester` |
   | 2 | Married on December 31, 2025? | `no` |
   | 3 | Single, widowed, or taking care of someone? | `single` |
   | 4 | Date of birth | `March 4, 1950` (or the Month / Day / Year boxes → **Send this date**) |
   | 5 | "You were born on March 4, 1950. Is that right?" | `yes` |
   | 6 | Legally blind? | `no` |
   | 7 | Anyone depend on you? | `no` |
   | 8 | **Did you get a W-2 form from a job this year?** | `yes` |

3. **The W-2 step appears.** Tick **I confirm this is not a real tax form.**, choose
   `data/fixtures/w2_01.jpg` under **Choose the photo of your W-2 (JPG or PNG)**, click **Add my W-2**.
4. Answer the remaining questions (9–24): `no` to every question, except
   *refund by bank account or paper check?* → `paper check`, *lived in the US for all of 2025?* →
   `yes`, *answering these questions yourself?* → `yes`.
5. After the last answer the photo is read, and the chat says a volunteer is checking: the case waits
   for the W-2 check (`EXTRACTION_REVIEW`).

**B. The volunteer** (http://localhost:8501 → **I'm a Kushim volunteer** → **Open the volunteer dashboard**)
1. Type your name in **Your name (shown in the case record)**.
2. The case is at the top, needing a volunteer: *"A W-2 reading needs to be checked against the
   photo."* Click **Open**.
3. Compare the photo with the amounts read: box 1 **30000.00**, box 2 **2000.00**. Choose **Accept: the
   amounts match the photo**, enter the tax year **2025**, tick **I compared the amounts with the photo,
   and this is a W-2.**, write a note (e.g. "Amounts match the photo."), click **Save decision**.

**C. Back in the chat** (same case ID; click **Check again** if the page is still waiting)

The chat shows **Your draft tax form**. Click any amount to see its formula, inputs and source.

## What you should see on the draft
| Line | Amount | Where it comes from |
|---|---|---|
| Filing status | Single | Rules, from the answers |
| 12d | 1 box (65 or older) | Rules |
| 1a / 1z wages | $30,000.00 | W-2 box 1 (the photo, checked by the volunteer) |
| 12e standard deduction | $17,750 | `calculate_standard_deduction` ($15,750 + $2,000) |
| 13b senior deduction | $6,000 | `calculate_senior_deduction` |
| 15 taxable income | $6,250 | 30,000 − 17,750 − 6,000 |
| 16 / 24 tax | $625 | `calculate_income_tax` |
| 25a / 33 withheld, total payments | $2,000.00 | W-2 box 2 |
| **34 refund** | **$1,375** | 2,000 − 625 |

Review passes the draft. The page says plainly that nothing has been filed.

## The automatic check
`python -m evals.runner --case eval-case-1-clean --case eval-case-1-line-amounts` runs the same
return without the browser (the answers and W-2 boxes come from `evals/cases.json`; that copy uses a
1955 birth date): line 1a $30,000 and 25a $2,000, Review passes. CI runs it on every push, and the
`compose` job runs the chat → photo → volunteer approval → draft flow inside Docker.

## If something differs
- **No key in `.env`:** the W-2 step says a volunteer will help; the photo is not read.
- **"I don't have it now"** instead of adding the photo: the case later pauses for a volunteer
  (`INCOME_NOT_READ`), because the W-2's income would otherwise be missing.
- The AI may misread a box: correct it in the volunteer's W-2 check before accepting.
