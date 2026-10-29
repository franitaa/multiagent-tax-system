# Eval case 1: clean minimal run

A single filer born in 1955 with one W-2 and nothing out of scope. Everything works and no
human is needed: the system produces a draft (it never files anything).

Case data: `eval-case-1-clean` in [evals/cases.json](../evals/cases.json).

## The data (fake)
| What | Value |
|---|---|
| Taxpayer | born 1955-03-14, single, not blind |
| Scope answers | no other tax forms |
| Document | W-2 `w2_01` ([data/fixtures/w2_01.jpg](../data/fixtures/w2_01.jpg), from the Extraction fixtures) |
| W-2 box 1 (wages) | $30,000.00 |
| W-2 box 2 (federal tax withheld) | $2,000.00 |

The taxpayer types:
1. "Hi, I need help with my 2025 return."
2. "I was born in March 1955, I am single and I have one W-2."

## Run it
```
python -m evals.runner --case eval-case-1-clean
docker run --rm silverfile python -m evals.runner --case eval-case-1-clean
```

## What you should see
```
PASS     eval-case-1-clean  Eval case 1 (clean minimal run): single filer born 1955 with one W-2, a draft is produced
```
- Route: `intake -> extraction -> rules -> computation -> review -> end`, with no human step.
- Rules: filing status `single`, eligible for Form 1040-SR, in scope, one age box (65+).
- Review: verdict `pass`. Status: `complete` (draft ready, nothing filed).
- Line 1a = $30,000.00 and line 25a = $2,000.00, each with a provenance record pointing
  to `w2_01.box_1` / `w2_01.box_2` (checked by `eval-case-1-line-amounts`).
- A trace of every agent call is written to `traces/<thread_id>.jsonl`.

## Status
- Passes now with the agents on `main`. Intake's answers and the W-2 box values come from the
  case file (stand-ins), so the case runs offline. The real Extraction reads `w2_01.jpg` with an
  image model, which needs an API key; with every agent real, run `python -m evals.runner --real-agents`.
- `eval-case-1-line-amounts` is pending until the real Computation agent is merged (the
  placeholder writes line 1a = 1000).
