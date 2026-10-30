# Status: orchestration (Person 1)

Updated 2026-10-30, after PRs #21 to #36 landed on `main`. All six agents exist; the graph, the human gate and the
review loop run end to end. Tests: about 1,100 pass; the remaining expected failures are the three pending evals.

## Done
- **Core (merged):** state contract, hub-and-spoke graph, runner with JSONL tracing, routing table, human gate with
  stop-only rules, parallel extraction with order-independent reducers, bounded review loop, loop guard.
- **Context management:** scoped views per agent (Rules sees only the facts it reads; Computation numeric facts and the
  filing status; Review numeric facts and the sources), Intake chat window of 6, deterministic rolling summary,
  `--no-context-strategy`, `docs/decisions/001-context-strategy.md`, `docs/metrics.md`.
- **Orchestrator invariants:** a case never ends "complete" without a filing status and an eligibility verdict
  (`ELIGIBILITY_UNDECIDED`, stop-only); after a volunteer answers `FILING_STATUS_AMBIGUITY` or `ANSWER_UNCERTAIN` the gate
  clears `eligibility`, so Rules decides again with the answer.
- **Failure handling:** a tax-tool server that cannot start ends the case as `halted_by_error` (nothing computed or filed;
  trace and audit entry, no traceback).
- **Integrated by the team:** Intake (real, wired into the chat page), Extraction (W-2 vision, `EXTRACTION_REVIEW`),
  Rules (reads Intake's names, maps filing status at its output, raises `ANSWER_UNCERTAIN`), Computation over MCP with
  provenance, Review/Audit (#30), CI and Docker, evals (`python -m evals.runner`), draft form, taxpayer chat with sessions
  saved on disk (#34), volunteer dashboard (#35), and API keys read only from `.env` (#32).
- **Docs:** `docs/handoff-contract.md` is current (Review, skipped documents, tools and transport, `EXTRACTION_REVIEW`,
  `reviewer`, `halted_by_error`); `docs/intake-rules-contract.md` records what Rules now does.

## Open
- **#27, income forms that are not read.** SSA-1099, 1099-INT and 1099-DIV are skipped by Extraction, so their amounts
  never reach the draft. Safety net (built): the lines say `NOT READ`, the draft form warns (#33), and the orchestrator
  pauses the case once for a volunteer (`INCOME_NOT_READ`) before Computation, also when a declared W-2 or 1099-R was never
  uploaded. The real fix is still open: Intake asks the amounts (typed, `direct user input`) and Computation uses them.
  Until then every such case needs a volunteer, and the chat has no upload step, so a chat case with a W-2 pauses.
- **Intake as the default:** `AGENTS["intake"]` is still the stub; only the chat page uses the real one (`live_agents()`).
  Two evals stay pending for it (tax advice, exploitation signs), plus `interest-conflict` (nothing compares answers with
  document amounts). Owner: Supriya, with a decision from orchestration.
- **Review does not check `rule_citations` yet** (planned; `docs/handoff-contract.md`).
- **Persistence:** chat sessions are saved in `runtime/team_checkpoints.sqlite` (#34), unencrypted, and nothing deletes old
  cases on a timer: schedule `python -m scripts.purge_cases --expired`. JiWon's chat and W-2 upload integration and the
  document gate were split out of #32 and are not merged; they come back as separate PRs, for review.
- **Volunteer dashboard (#35):** no login, so a taxpayer can reach it from the start page; the volunteer's name is not verified;
  it cannot resolve `EXTRACTION_REVIEW` (it says where to go). A staff passcode is a team decision.
- **For the instructor:** the assignment's context section talks about "10 invoices", which does not match a tax project.
  We treat it as "a long session or a batch of many documents". Is that acceptable?

## Next (orchestration)
- Telemetry dashboard (bonus, read-only, over `traces/` and the audit log; not an agent): built, PR #38; spec in
  `docs/telemetry-dashboard-spec.md`.
- Review the #27 decision once the team has chosen, and the Review hold if it is chosen.
- Review JiWon's document-gate and chat/W-2 upload changes when they come back as separate PRs.

## Process
Two early Rules commits went straight to `main` without a PR. Suggest branch protection requiring PRs.
