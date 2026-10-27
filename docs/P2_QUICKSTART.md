# Team integration note

This package now exposes the same factories from `src.memory`. The team demo uses `runtime/team_checkpoints.sqlite`. Use `load_resume_context(graph, case_id)` for the parent graph; `CaseMemory` remains a separate optional answer log. See P3_INTEGRATION.md for tool registry and graph wiring.

# P2 integration: case ID, checkpointer, and resume summary

**Use your existing case ID as the session ID and LangGraph thread ID.**
Do not generate a different ID on page refresh. The user must select/recover the same case;
P1/P2 must implement that selection. A case ID does not identify or authenticate a person.

## Files and functions to import

```python
from silverfile_extraction.checkpointer import sqlite_checkpointer, case_config
from silverfile_extraction.case_memory import CaseMemory, StaleRevisionError
```

Install this module with `python -m pip install -e path/to/silverfile-document-extraction`.
Keep its `src/silverfile_extraction` package intact when integrating into the team repository.
Do not replace P4's state schema or P6's root requirements file with this demo's files.

## 1. Replace the parent's in-memory checkpointer

Where P1 currently compiles the **team's** graph:

```python
with sqlite_checkpointer("runtime/team_checkpoints.sqlite") as saver:
    graph = team_graph_builder.compile(checkpointer=saver)
    config = case_config(case_id)  # exactly {"configurable": {"thread_id": case_id}}
    snapshot = graph.get_state(config)
    # All graph.invoke(), graph.get_state(), and Command(resume=...) calls belong
    # INSIDE this context, while the database connection remains open.
```

`team_graph_builder` is P1's existing StateGraph builder, not a function exported here.
This is the synchronous API. An async server must use a separately managed AsyncSqliteSaver.
For a Streamlit prototype, reopening the context and compiling the same builder on each rerun
is acceptable. Keep the DB path fixed and writable. Do not create a new database per rerun.

For a graph interrupt, P1 resumes using `graph.invoke(Command(resume=validated_answer), config)`.
Loading a page is a read-only `get_state` operation, not a fresh `invoke` with empty input.
Graph checkpoints preserve whatever P4 puts in graph state; they do not automatically invent
a `messages` channel or a taxpayer-friendly summary.

Keep `runtime/team_checkpoints.sqlite` separate from the extraction-only demo's
`runtime/direct_vision_checkpoints.sqlite`. Two differently shaped graphs must not share a case namespace.

## 2. Save answers and the next question

The new answer store is a separate durable audit log, not a replacement graph state.
It does not invoke any model and it does not decide filing status or which question comes next.

```python
memory = CaseMemory("runtime/intake_memory.sqlite")
state = memory.load_case(case_id)

# On a new submitted answer, assign one UUID and retain it for retries of that
# SAME submission. Create a new UUID only for a new answer or a correction.
state = memory.save_answer(
    case_id, "Q1", "yes",
    actor="test-taxpayer", event_id=client_submission_id,
    next_question_id="Q2", expected_revision=state["revision"],
)
```

P2 supplies the next question based on its current dialogue logic. There is no hard-coded
question sequence here because Q2/Q3, spouse questions, and dependent questions are conditional.
Use `Q9:dep1`, `Q10:dep1`, `Q12:dep1` and separate IDs for other dependents.

Saving a changed answer with a **new** event ID retains the original answer in `answer_history`.
Saving the same submission again with the **same** event ID is idempotent. A stale revision raises
`StaleRevisionError`: reload and show the current answer rather than silently overwriting it.
P2/P1 remain responsible for invalidating downstream tax calculations after an answer changes.

For Q19 and other direct monetary inputs, pass a decimal string and `monetary=True`. A five-field
P5 provenance payload is recorded with the actor, question, event ID, and UTC timestamp.
Do not use a float. Q20 is a yes/no question in the provided script; add a separately agreed field
for adjustment amounts with P4 rather than replacing that answer with an amount.

## 3. Resume on Friday

```python
resume = memory.get_resume_context(case_id)
# P2 displays resume["summary"] in its own taxpayer UI.
# P2 renders the question identified by resume["next_question_id"].
# Original values and history are available through memory.load_case(case_id).
```

Example summary: "Welcome back. We recorded answers about marital and filing information,
birth dates and sight. We saved your place so you can continue."

The summary intentionally excludes raw birth dates, SSNs, and amounts. It reports topics with
recorded answers, not that a whole topic or return has been completed. A `None` next question
is not automatically treated as a completed return; check the explicit stage and graph state.

To go back without deleting answers:

```python
memory.set_progress(case_id, next_question_id="Q1", expected_revision=state["revision"])
```

To record a human pause, P1/P2 use stage `paused` and explicit `pending_review` codes. This
records progress only; **P1 still calls LangGraph interrupt**. P2 still detects advice requests,
uncertainty, exploitation, and volunteered SSNs. This store rejects non-test SSNs and unsolicited
SSNs, but does not replace P5's security.py. Only requested Q12 fields can store a synthetic SSN.

## 4. Recovery after a crash between store and graph

Write the answer store first. Pass its returned revision/event ID into the parent state using
the field names agreed with P4. When resuming, compare that revision with the graph's last handled
revision. If a saved answer has not reached the graph, replay its SAME event ID through the normal
handler; do not ask for or save the answer a second time. Do not automatically resume a human
interrupt with a taxpayer answer intended for a different question.

These are two databases, not a single cross-database transaction. P1 must implement the replay
check in the parent handler. This package provides idempotent answer writes, not exactly-once
execution of arbitrary external actions. Full team integration cannot be verified without P1/P4 code.

## 5. Run acceptance checks before calling MEM-1 ready

```bash
python examples/checkpointer_demo.py pause
python examples/checkpointer_demo.py show
python examples/checkpointer_demo.py resume
python examples/p2_answers_demo.py save
python examples/p2_answers_demo.py resume
python -m unittest discover -s tests -v
```

Each command starts a new process. The first check should show `pending: true` after pause,
then `pending: false` and `answer: yes` after resume. The answer-store demo should retain Q1
and point to Q2. Do not rerun `pause` on an already used case; use `--case MEM1-NEW` if needed.

**Validation status:** answer-store process-restart tests were executed in the authoring environment.
Actual LangGraph integration still requires the dependency-enabled checks above. An implemented
factory is not evidence of a successful six-agent integration.

