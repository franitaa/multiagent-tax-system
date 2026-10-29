# multiagent-tax-system
 Multi-agent system to assist with preparation of form 1040-SR.

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

## Eval cases
End-to-end cases (a clean return, the spouse-died case, each escalation) are in [evals/cases.json](evals/cases.json); how to read and add them: [evals/README.md](evals/README.md).

```
python -m evals.runner                       # PASS / FAIL / PENDING for every case
docker run --rm silverfile python -m evals.runner
```
