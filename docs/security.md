# Security and privacy: what is protected, how, and what is not

Owner: Person 5. Code: `security.py`, `document_security.py`, `src/audit.py`, `src/retention.py`,
`src/orchestration/validate.py`, and the runner (`src/orchestration/runner.py`), which applies them.
Chat messages are cleaned in the `messages` reducer in `src/state.py` (`append_messages`).

## What is protected
| Risk | Defence | Where |
|---|---|---|
| A real SSN entered by mistake | Only 900-999 test SSNs are accepted; real-looking ones are removed and the user told why | `security.py`, Intake, chat page |
| A real SSN in a chat message, even when the caller skips the chat page | Every new message is cleaned as it enters state: an SSN-like number outside 900-999 (dashes, spaces or plain digits) becomes `[number removed]`; practice numbers stay | `security.remove_real_ssns`, `src/state.py` |
| Identifiers in documents and traces | Redaction of SSN/EIN/email/phone; traces hold field names, never values | `security.redact_pii`, runner |
| Identifiers in escalation reasons and volunteer notes | The runner redacts these free-text fields (including queued escalations) before an update reaches state or a checkpoint; the audit log redacts its own copy | `Runner._redact_free_text` |
| Instructions hidden in a document (prompt injection) | Text is labelled as data, invisible control characters removed, instruction-like text flagged and audited | `document_security.py`, runner |
| An agent talked into misbehaving | Write allow-list per agent, then shape checks: size, plain data, known handoff targets and conditions, **no dollar amount without a provenance record** | `access.py`, `validate.py` |
| Nobody can say who decided what | Append-only, hash-chained audit log per case | `src/audit.py` |
| Personal data kept forever | Delete a case everywhere, expire idle cases, clear stale uploads | `src/retention.py` |

## Prompt injection
Detection is a flag for a human, never a guarantee, and flagged text is **not rewritten** so a
reviewer sees what the document said. The stronger claim is containment, tested with a corpus of
attacks and with agents that *obey* the document (`tests/test_prompt_injection.py`): they cannot
write fields outside their allow-list, return malformed or oversized output, name an unknown
handoff target or escalation, end the case, or put a dollar amount in `computed` without its
provenance. What containment cannot stop: a model that is persuaded to misreport a value *inside*
its own allowed fields. Review (independent recomputation) and the human gate are the backstop.

## Audit log
`<trace dir>/audit/<case>.jsonl`. Events: `escalation_raised`, `paused_for_volunteer`,
`volunteer_decision` (who, condition, decision, redacted note, names of the fields resolved, never
their values), `document_flagged`, `draft_ready`, `case_stopped`, `draft_form_written`,
`case_purged`. Actors: `agent:<name>`, `volunteer:<name>`, `system:<job>`. A volunteer is named by
passing `"reviewer": "<name>"` in the resume value of the human gate; without it the entry says
`volunteer:unidentified`. The dashboard should also call
`AuditLog.record(case_id, "viewed", actor="volunteer:<name>")` when a case is opened.
`AuditLog.verify(case_id)` returns problems if an entry was edited or removed from the middle.
It holds no answers, amounts or document text, so it is kept after a case is purged.
Limits: deleting the end of the file is not detected by the chain, and the `reviewer` name is
whatever the caller supplies (there is no login yet).

## Retention
Policy: a case idle 30 days is expired; an upload never saved to a case is removed after 24 hours.
```
python -m scripts.purge_cases --case SF-482-735 --reason "taxpayer asked" --actor "volunteer:Pat"
python -m scripts.purge_cases --expired --dry-run      # list what would go
python -m scripts.purge_cases --expired                # apply the policy (schedule this)
```
A purge removes the case's graph state, Intake answers, traces, draft forms, its document images
(`runtime/documents/`) and the uploads it was read from (`runtime/uploads/<sha>.png`). Anything another
case still uses is kept. It then writes a `case_purged` audit entry with counts only. Stale-upload
cleanup skips any upload a saved case still points at, so an active case is never broken by it.
Nothing runs by itself: schedule `--expired` (cron, Task Scheduler, a container job). It must run from
the repository folder, because the runtime paths are relative. For example, a daily Windows Task
Scheduler action: `cmd /c cd /d "<repo folder>" && "<repo folder>\.venv\Scripts\python.exe" -m scripts.purge_cases --expired`.
Limits: this deletes rows and files; it does not securely wipe disk blocks or backups.

## Not done
- Dependents' test SSNs are stored unencrypted in the checkpoint database.
- Redaction does not cover names or addresses, and is regex-based.
- No authentication: a case ID is not a secret, and volunteer names are not verified.
