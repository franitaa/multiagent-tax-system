# Decision 002: which Intake runs by default, and the assumptions we made without asking

Date: 2026-10-30. Owner: Francesca (orchestration).

## 1. The stub Intake stays the offline default; every entry point that talks to a person uses the real one
`AGENTS["intake"]` is the stub (it asks one canned question). `live_agents()` returns the same set with the real
Intake (the 24-question interview). These use `live_agents()`: the taxpayer chat, the shared extraction service
(`make_shared_service`) that the chat and the volunteer dashboard both use, the CLI, and the evals' `real_intake` mode.

Why we do not switch the default:
- The scenarios, the context metrics (`docs/metrics.md`) and many of the tests depend on a short, deterministic Intake.
  A real interview of 24 questions would change every one of those numbers and slow the suite, with no change for a user.
- A user can only reach the graph through an entry point that already uses the real Intake, so nobody can run the
  stub by accident.

Checks that hold this decision: the evals that need the real Intake (tax advice, exploitation signs)
run with `"real_intake": true` and pass (15 of 15 on `main`), and `tests/test_e2e_intake.py`
runs the real Intake against the real Rules.

What would change it: a new entry point (an API, a second page). It must call `live_agents()`; if it builds a graph
without arguments it gets the stub.

## 2. Assumption not confirmed by the instructor: "10 invoices"
The assignment's context section talks about "10 invoices", which does not match a tax project. We are not asking the
instructor, so we record our reading and what it affects:
- **Our reading:** "a long session or a batch of many documents". The context strategy is measured on a
  30-turn interview and a case with 12 documents (`docs/metrics.md`).
- **What depends on it:** only the measurement scenarios (`scripts/`, `docs/metrics.md`). No rule in the product depends on it.
- **If the reading is wrong:** the strategy is unchanged; only the scenario sizes in the metrics script change, and
  the numbers in `docs/metrics.md` are regenerated.
- **Disclosed in the report:** the team should state this assumption where the context results are presented.

## 3. The gate requires a filing status on "Continue" for `FILING_STATUS_AMBIGUITY`
Before, a volunteer could continue without choosing a status; Rules then found none and the case stopped as
`ELIGIBILITY_UNDECIDED`. Now the gate refuses a bare "continue" and asks again with an error
(`src/orchestration/human.py`; tests in `tests/test_hitl.py`). "Stop" still needs nothing. The volunteer dashboard
already asked for a status, so the page does not change.
