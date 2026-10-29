# Eval case 2: a human-in-the-loop event, resolved

The taxpayer's husband died in March 2025. Whether she files as married filing jointly,
qualifying surviving spouse or single is a filing-status ambiguity, so the system does not
guess: it pauses (LangGraph interrupt) and a volunteer decides. After the volunteer's answer
the run continues to a draft.

Case data: `eval-case-2-spouse-died` in [evals/cases.json](../evals/cases.json).

## The data (fake)
| What | Value |
|---|---|
| Taxpayer | born 1950-02-02, not blind, widowed; spouse died in 2025 |
| Scope answers | no other tax forms |
| Document | W-2 `w2_02` ([data/fixtures/w2_02.jpg](../data/fixtures/w2_02.jpg), from the Extraction fixtures) |
| W-2 box 1 / box 2 | $31,234.00 / $2,087.00 |

The taxpayer types:
1. "Hi, I need help with my 2025 return."
2. "My husband passed away in March, and I am not sure how to file."

## Run it (answers the interrupt automatically)
```
python -m evals.runner --case eval-case-2-spouse-died
```
```
PASS     eval-case-2-spouse-died  Eval case 2 (HITL, resolved): spouse died during 2025, a volunteer decides the filing status
```

## How to resolve it by hand
1. **Start the case.** The graph stops before any amount is computed:
   ```python
   from langgraph.types import Command
   from evals import runner
   from src.graph import build_graph

   case = next(c for c in runner.load_cases() if c["id"] == "eval-case-2-spouse-died")
   graph = build_graph(agents=runner.stand_ins(case))
   config = {"configurable": {"thread_id": "demo-eval-2"}}

   paused = graph.invoke(runner.graph_input(case), config)
   paused["status"]                     # 'awaiting_human'
   paused["__interrupt__"][0].value     # what the volunteer sees
   ```
   ```
   {'condition': 'FILING_STATUS_AMBIGUITY', 'reason': 'Widowed filing status requires human review',
    'raised_by': 'rules', 'options': ['continue', 'stop'],
    'note_required_for_continue': True, 'resolution_fields': ['filing_status']}
   ```
2. **The volunteer decides.** A spouse who died during the tax year still counts as married
   for that year, so a joint return is allowed. The volunteer answers `continue`, gives the
   filing status, and writes a note (required: it goes in the audit record):
   ```python
   final = graph.invoke(Command(resume={
       "decision": "continue",
       "note": "Volunteer confirmed the spouse died in 2025; a joint return is allowed for that year.",
       "resolution": {"filing_status": "married_filing_jointly"},
   }), config)
   ```
   Allowed filing statuses: `single`, `married_filing_jointly`, `married_filing_separately`,
   `head_of_household`, `qualifying_surviving_spouse`. Answering `continue` without a note, or
   with an unknown status, is refused and the same question is asked again.
3. **Check the result.**
   ```python
   final["status"]              # 'complete'
   final["human_decisions"]     # the decision, note and filing status, kept for the audit
   final["facts"]["filing_status"]
   # {'value': 'married_filing_jointly', 'source': 'human:FILING_STATUS_AMBIGUITY'}
   ```
   Route: `intake -> extraction -> rules -> human -> computation -> review -> end`.

To stop instead (e.g. the volunteer wants to see the death certificate first):
`{"decision": "stop", "note": "..."}`. The case ends with status `halted_by_human`.

The same case with the scenario script: `python -m scripts.run_scenarios spouse-died`.

## Status
- Passes now: the interrupt fires, the volunteer's answer is validated and recorded, and the
  run completes.
- **Known gap**, tracked by the pending case `eval-case-2-status-reaches-draft`: the human gate
  stores `married_filing_jointly`, but Rules only recognises short names (`mfj`), so
  `eligibility.filing_status` stays `undetermined` on the draft. Fix in either
  `src/orchestration/human.py` or `src/agents/rules.py` (one set of names for both).
- Intake's answers and Extraction's box values come from the case file until the real agents
  are connected; the fixture image is in Extraction's PR (#15) until it is merged.
