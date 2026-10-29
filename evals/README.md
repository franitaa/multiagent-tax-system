# Eval cases

The two cases the assignment asks for (§5.2) are `eval-case-1-clean` (a clean minimal run)
and `eval-case-2-spouse-died` (a HITL event that is resolved); how to run and resolve them:
[demo/eval_case_1.md](../demo/eval_case_1.md) and [demo/eval_case_2.md](../demo/eval_case_2.md).
The other cases cover each escalation condition.

`cases.json` holds end-to-end cases. `python -m evals.runner` runs each one through the real
graph (orchestrator, human gate, every agent on `main`) and checks the outcome. CI runs them
on every push, and `tests/test_evals.py` runs them under pytest too.

## Results
| Result | Meaning |
|---|---|
| `PASS` | The case behaves as expected. |
| `FAIL` | A case that should pass does not. CI goes red. |
| `PENDING` | The case has a `pending` note: the behaviour is not built yet. Does not fail CI. |
| `FIXED` | A pending case now passes. Remove its `pending` note so it is guarded from now on. |

## A case
```json
{
  "id": "under-65-not-eligible",
  "title": "Taxpayer born 1970 is not eligible for Form 1040-SR: stopped by a human",
  "messages": ["Hi, I need help with my 2025 return.", "I was born in 1970 and I am single."],
  "facts": {"taxpayer_birth_date": "1970-06-01", "taxpayer_blind": "no", "...": "..."},
  "documents": [{"id": "w2-1", "kind": "W-2", "fields": {"box_1": 52000.0, "box_2": 6000.0}}],
  "resume": [{"decision": "stop", "note": "Not a 1040-SR return; referred elsewhere."}],
  "expect": {"interrupts": ["OUT_OF_SCOPE"], "status": "halted_by_human", "no_computed_lines": true}
}
```

- `messages`: what the taxpayer types.
- `facts` (optional): the answers Intake would record, using the names in
  [docs/answer-names.md](../docs/answer-names.md). When given, they stand in for Intake.
- `documents`: each document's `kind` and, optionally, the box `fields` Extraction would read.
  When given, they stand in for Extraction. Box names follow docs/handoff-contract.md.
  `fixture` (optional) names the fixture file the values come from.
- `resume`: the volunteer's answer to each interrupt, in order (same format as the human gate).
- `pending` (optional): why the case cannot pass yet, and whose work it waits for.

Stand-ins let the cases test Rules, Computation, Review and the orchestrator on known inputs
while Intake and Extraction are still placeholders. `python -m evals.runner --real-agents`
ignores them.

## What `expect` can check
| Key | Checks |
|---|---|
| `interrupts` | The escalations a human saw, in order (`[]` = none). |
| `status` | Final status: `complete` or `halted_by_human`. |
| `route_starts_with` | The first hops of the route, e.g. `["intake", "extraction", "rules"]`. |
| `eligibility` | Exact values in Rules' `eligibility` (filing status, boxes, ...). |
| `rules_include` | Rule names Rules applied (`eligibility.rule_citations[].rule`). |
| `lines` | Form line values, within $0.50. |
| `no_computed_lines` | Nothing was computed (the case stopped first). |
| `review_verdict` | Review's verdict, `pass` or `fail`. |
| `human_decisions` | The volunteer's decisions, as `"CONDITION:decision"`. |

Fake data only: no real names, and SSNs only in the test range 900-999.
