# SilverFile (multiagent-tax-system)

A multi-agent system, built in LangGraph (Python), that helps prepare a **draft** US Form 1040-SR for
seniors. It never files anything, never gives tax advice, never states an unsourced dollar amount,
sends defined cases to a human, and handles only the in-scope return profile. Test data only: no real
SSNs.

## Teammates start here
If you own an agent, read [docs/handoff-contract.md](docs/handoff-contract.md) first: what state you may
read and write, the handoff format, how to escalate to a human, and how to replace your stub.
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

## How it works
Six agents, one hub. The **orchestrator** is the only thing that chooses the next hop and decides when to
stop; it does not extract, compute, or talk to the user. The other five (Intake, Document Extraction,
Eligibility & Rules, Computation, Review/Audit) never call each other: each returns a state update plus
a handoff request, which the orchestrator validates. Every agent call goes through one wrapper
(`src/orchestration/runner.py`) that scopes what the agent can see, enforces its read/write/tool
allow-lists, and writes a JSONL trace to `traces/`.

What the graph demonstrates:
- **Conditional routing:** the next hop is a pure function of state (`src/orchestration/router.py`).
- **Parallel branch:** extraction fans out one worker per document and merges with an order-independent reducer.
- **Bounded cycle:** Review sends work back to Computation, at most 3 times by default.
- **Loop guard:** a pathological handoff loop escalates to a human.
- **Human in the loop:** a LangGraph interrupt for out-of-scope items, unresolved conflicts, 1099-R box 2b,
  tax-advice requests, filing-status ambiguity (such as a spouse who died), and signs of exploitation.
- **Context management:** each agent gets the smallest view it needs
  ([decision record](docs/decisions/001-context-strategy.md), [measurements](docs/metrics.md)).

<!-- graph:start -->
```mermaid
---
config:
  flowchart:
    curve: linear
---
graph TD;
	__start__([<p>__start__</p>]):::first
	orchestrator(orchestrator)
	human(human)
	intake(intake)
	extraction(extraction)
	rules(rules)
	computation(computation)
	review(review)
	__end__([<p>__end__</p>]):::last
	__start__ --> orchestrator;
	computation --> orchestrator;
	extraction --> orchestrator;
	human --> orchestrator;
	intake --> orchestrator;
	orchestrator -. &nbsp;end&nbsp; .-> __end__;
	orchestrator -.-> computation;
	orchestrator -.-> extraction;
	orchestrator -.-> human;
	orchestrator -.-> intake;
	orchestrator -.-> review;
	orchestrator -.-> rules;
	review --> orchestrator;
	rules --> orchestrator;
	classDef default fill:#f2f0ff,line-height:1.2
	classDef first fill-opacity:0
	classDef last fill:#bfb6fc
```
<!-- graph:end -->

*Generated from the compiled graph by `python -m scripts.draw_graph`; every agent returns to the orchestrator
(solid), and only the orchestrator chooses the next hop (dotted).*

## Run it
Python 3.12 is what we use (3.10 or newer should work).

```
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pytest                                              # all tests, offline and fast
```

Scenarios (all offline; each writes a trace to `traces/`):

```
.venv/bin/python -m scripts.run_scenarios clean               # a clean case to "DRAFT READY"
.venv/bin/python -m scripts.run_scenarios interrupt           # pauses for a human, then resumes
.venv/bin/python -m scripts.run_scenarios spouse-died         # filing-status ambiguity, volunteer supplies the status
.venv/bin/python -m scripts.run_scenarios clean --no-context-strategy   # every agent gets the full state
.venv/bin/python -m scripts.measure_context                   # regenerates docs/metrics.md
.venv/bin/python -m scripts.draw_graph                        # regenerates the diagram above
```

A trace line (`traces/<thread_id>.jsonl`) records the agent, the handoff (from, to, reason), the state
fields read and written, duration, and estimated input/output tokens. It stores field names, never values.

## Layout
| Path | What |
|---|---|
| `src/state.py` | The shared state contract (fields, reducers, escalation conditions) |
| `src/graph.py` | The hub-and-spoke graph |
| `src/orchestration/` | Router, orchestrator, loop guard, human gate, runner/tracing, access policy, context views |
| `src/agents/` | The five agents (some are still stubs) |
| `tests/` | Tests, including the decision table and `test_merge_order.py` |
| `docs/` | [Contract](docs/handoff-contract.md), [decision record](docs/decisions/001-context-strategy.md), [metrics](docs/metrics.md), [Intake/Rules fact names](docs/intake-rules-contract.md), [status](docs/STATUS.md) |

## Rules for contributors
Feature branches and pull requests; nothing goes straight to `main`. Run `pytest` before every commit.
Secrets live only in `.env` (see `.env.example`); never commit it or traces containing personal data.
