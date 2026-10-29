# SilverFile: project context for Claude Code

## What this is
University team project (6 people). A LangGraph (Python) multi-agent system that helps prepare a DRAFT US Form 1040-SR for seniors. Fake application: only test SSNs 900-xx-xxxx to 999-xx-xxxx are accepted.

## Business rules (never weaken these; treat violations as blockers)
1. Never file anything. Output is a draft plus an audit record for a human.
2. Never give tax advice (planning, optimisation, "should I..."). Offer to note the question for a volunteer.
3. Never assert a dollar amount that cannot be sourced. Every money value carries a provenance record.
4. Always route to a human (LangGraph interrupt) in the escalation cases below.
5. Only handle the in-scope return profile. Everything else escalates.
6. Exactly six agents, none merged: Orchestrator, Intake, Document Extraction, Eligibility & Rules, Computation, Review/Audit.

## Escalation conditions (HITL via interrupt)
Out-of-scope item (Schedule A/C/D/E, 1099-NEC, digital assets, foreign income, amended/prior-year/state returns, 1099-R with box 2b checked); unresolved user-vs-document conflict; request for tax advice; filing-status ambiguity (esp. spouse died in the tax year); signs of financial exploitation or third-party pressure.

## Architecture
Centralised orchestration (hub-and-spoke). The Orchestrator is the only thing that decides the next hop and when to stop. It must not extract, compute, or talk to the user. Agents never call each other; they return state updates plus a handoff request.
Every agent call goes through one wrapper (src/orchestration/runner.py) that logs to traces/, counts tokens, enforces that agent's allowed tools, and records the handoff (from, to, reason).

## Context management (explicit decision, see docs/decisions/001-context-strategy.md)
Each agent receives a scoped view of state, not the whole state. Rolling summary of decisions plus selective recall. A --no-context-strategy flag disables it for measurement. Input-token counts per call are logged and summarised in docs/metrics.md.

## Layout
src/state.py, src/graph.py, src/memory.py, src/agents/, src/orchestration/, data/, evals/, tests/, traces/, docs/, demo/. Required tests include tests/test_merge_order.py and tests/test_decision_table.py.

## Working rules
- Python 3.11+, virtualenv in .venv, secrets only in .env (never commit; keep .env.example current).
- Check the installed langgraph version's docs before using an API; do not guess signatures.
- Small commits, feature branches (p1/<topic>), open PRs, never push straight to main. Commit under my git identity. Ask before pushing.
- Stub other people's agents; do not implement tax logic, intake questions, extraction or review logic unless asked.
- Run pytest before every commit.
- If you own an agent, read docs/handoff-contract.md first.
