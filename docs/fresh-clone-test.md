# Fresh-clone test

A check that the project works for someone who has only the repository: clone it, install it, run
every documented command. Run by Shruti (MLOps/DevOps) with Claude Code.

## Run 1: Fri Oct 30, 2026, `main` at `08b4da6` (after #69)
macOS, Python 3.11.16, Docker Desktop. A new clone in an empty folder; a blank `.env` from
`.env.example` (no API key) for the app checks.

| Step | Command | Result |
|---|---|---|
| Clone | `git clone https://github.com/franitaa/multiagent-tax-system.git` | ok |
| Install | `python3.11 -m venv .venv`, `pip install -r requirements.txt` | ok |
| Tests | `python -m pytest -q` | 1369 passed |
| Eval cases | `python -m evals.runner` | 15 pass, 0 fail, 0 pending |
| Clean case | `python -m scripts.run_scenarios clean` | `DRAFT READY (nothing was filed)` |
| Eval case 2 | `python -m scripts.run_scenarios spouse-died` | `FILING_STATUS_AMBIGUITY` pause, resolved as married filing jointly, `DRAFT READY` |
| App, local | `streamlit run src/ui/silverfile_home.py` | answers on http://localhost:8501; start page, taxpayer chat, volunteer dashboard and telemetry all draw without an error |
| App, Docker | `docker compose up --build` | one container, `127.0.0.1:8501`; eval cases inside it: 15 pass, 0 fail |
| Repository left clean | `git status` | nothing written into the clone |

Both demo journeys (`demo/eval_case_1.md`, `demo/eval_case_2.md`) were also run through the chat and
volunteer-dashboard code with the offline W-2 reader: case 1 finishes with wages $30,000 and a refund
of $1,375; case 2 pauses for the filing status and the W-2 check and finishes as married filing jointly
with a $33,100 standard deduction. Review passes both.

## Real AI reading of a W-2 (Fri Oct 30, 2026)
`python -m scripts.verify_chat_extraction --provider anthropic` with a key in `.env` (one paid call, on
the fictional `data/fixtures/w2_01.jpg`), on a local copy of `main` that already had the chat upload
(#56) and the shared extraction service (#39):

```
OK  the interview recorded the W-2 answer and the upload was accepted
OK  the case waits for a volunteer to check the reading: status=awaiting_human, escalation=EXTRACTION_REVIEW
OK  box 1 read as 30000.00: read 30000.0
OK  box 2 read as 2000.00: read 2000.0
OK  the draft is complete after the review: status=complete
OK  line_1a equals box 1: 30000.0
OK  line_25a equals box 2: 2000.0
OK  the traces and audit log are in the chat's trace folder
ALL CHECKS PASSED
```
The OpenAI provider was not run.

## To repeat it
Follow [for-graders.md](for-graders.md) in a new, empty folder (not inside an existing clone: pytest
searches the whole project folder, so a copy inside it makes every test appear twice).
