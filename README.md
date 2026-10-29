# multiagent-tax-system

## Teammates start here
If you own an agent, read [docs/handoff-contract.md](docs/handoff-contract.md) first: what state you may read and write, the handoff format, how to escalate to a human, and how to replace your stub.
Project status: [docs/STATUS.md](docs/STATUS.md).

## Run with Docker
No local Python needed. The image is built and checked in CI on every push.

```
docker build -t silverfile .
docker run --rm silverfile                                    # a clean case to "DRAFT READY"
docker run --rm silverfile pytest -q                          # all tests, inside the container
docker run --rm -p 8501:8501 silverfile streamlit run src/ui/taxpayer_chat.py
                                                              # taxpayer chat page: http://localhost:8501
```

Secrets are never built into the image; pass them at run time with `--env-file .env`.

## P3 document extraction workbench
This folder combines the team files supplied in this conversation with P3's W-2 extraction and memory implementation. It is an integration candidate, not a completed six-agent tax product. **The supplied Intake, Computation and Review agents still contain stubs.** A `complete` graph status does not mean a valid return has been prepared.

## Windows / VS Code

1. Extract into a **new folder**, leaving your existing team checkout untouched.
2. Open the folder containing `start.py` in VS Code.
3. Open Terminal → New Terminal and run:

```powershell
python start.py
```

Python 3.11+ is required. The launcher installs dependencies into this folder's `.venv`. No Tesseract, Docker, activation command or source-code editing is required.

4. Open http://127.0.0.1:8501.
5. Enter your OpenAI API key in the sidebar. Choose a new case ID.
6. Upload `data/fixtures/w2_01.jpg`, confirm fictional data and click **Read W-2 image**.
7. Compare the amounts, fill in the reviewer/note, confirm visual verification and save the review.
8. Restart with the same case ID to inspect persisted results.

The workbench uses the **team graph**, access policies, parallel extraction node, runner and human gate. For this P3 demo only, it supplies fictional age 70 / Single facts and skips Intake. It accepts one new W-2 per case; the underlying team graph supports multiple document workers. Use a new ID for another image.

## What was connected

- `src/agents/extraction.py` calls a registered P3 tool, rather than returning a hard-coded amount.
- Real images go to OpenAI; deterministic synthetic text fixtures exist only for the offline team tests.
- The result uses `extracted[doc_id].fields.box_1` etc., with the team's five provenance fields. Exact monetary values stay decimal strings.
- The Orchestrator sends `EXTRACTION_REVIEW` to its human gate. Each document must be approved separately. Corrections update the extracted record and preserve the original.
- The runner records actual provider token usage for image extraction, keeping estimates labelled for other agents.
- The demo supplies SQLite persistence to the team's graph. P2 can use `src.memory` for checkpointer factories, answer storage and a read-only resume summary.

## Privacy and operational limits

Use **fictional test documents only**. The whole image is normalized and saved locally after your confirmation, then sent to OpenAI. This version retains the confirmed upload to allow retry/restart. Model-based SSN screening occurs after transmission; it is not reliable redaction or a guarantee that all real identifiers are blocked. This differs from the old standalone service, which saved only after model validation. Never upload real tax documents.

The manual API key stays in process/session memory; it is not placed in graph state, traces or exported records. Calls may incur API charges. `store=False` is used, but does not promise zero provider retention. Case IDs are not authentication. Keep this classroom UI on localhost.

Runtime images, databases and traces are under `runtime/` and ignored by Git. Do not commit `.env`, keys, `.venv` or runtime data. This ZIP contains no API key and does not migrate old checkpoints.

## Validate before merging

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

For the P3-only unit suite:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests_p3 -v
```

See [P3_INTEGRATION.md](docs/P3_INTEGRATION.md), [P3_CHANGED_FILES.md](docs/P3_CHANGED_FILES.md) and [VALIDATION.md](docs/VALIDATION.md). The common graph/security-policy/human-gate changes must be reviewed by P1 before merging into the team branch. No commit or push was performed.
