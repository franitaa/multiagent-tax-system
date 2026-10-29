# P3 integration guide

## Scope

This integration adds W-2 image extraction, typed monetary evidence, mandatory human verification, durable memory, and usage reporting. It does not replace the team's Intake/Rules/Computation/Review logic. The standalone root `computation_agent.py` supplied by P5 is still not the agent registered in `src/agents/__init__.py`; the registered Computation and Review agents remain stubs.

## P1: graph and tools

The existing `run(view, tools) -> dict` signature is retained. The tool registry is injected per graph instance, so credentials are not global shared state:

```python
from src.graph import build_graph
from src.p3.bridge import P3Tools
from src.memory import sqlite_checkpointer, case_config
from silverfile_extraction.vision import VisionReader

reader = VisionReader(api_key)  # key supplied by your server/UI, never in SilverState
runtime_tools = P3Tools('runtime', reader)
try:
    with sqlite_checkpointer('runtime/team_checkpoints.sqlite') as saver:
        graph = build_graph(checkpointer=saver, tool_registry=runtime_tools.registry())
        # Keep all graph.invoke/get_state/resume calls inside this context.
finally:
    reader.close()
```

`runtime_tools.upload(image_bytes, synthetic_confirmed=True)` returns a document reference for `documents`. It writes only under the configured runtime directory and uses hash handles, not caller-supplied filesystem paths. Pass `synthetic_confirmed=True` only after the user explicitly confirms fictional data and transmission. Keep upload operations outside an interrupting node to avoid repeated side effects.

The default graph checkpointer remains InMemorySaver for backward-compatible tests. The UI **explicitly passes SQLite**. P2 must do the same; calling plain `build_graph()` is not durable. The registry defaults to the strict deterministic text-fixture parser for offline tests, never a fabricated live amount.

Images are extracted once per pending document via the existing parallel Send workers. No agent calls another agent. The tool-backed image path returns `needs_review`; the agent sets the additional `EXTRACTION_REVIEW` condition with `document_id`. The Orchestrator performs the interrupt in `human.py`.

## P1: review resolution

Each queued document review is distinct, even if an earlier document was approved. A prior generic condition name cannot approve another document. Resume the same thread:

```python
from langgraph.types import Command
answer = {
    'decision': 'continue',
    'note': 'Compared every amount with the original synthetic W-2.',
    'resolution': {
        'document_id': pending_payload['document_id'],
        'review': {
            'action': 'accept', 'reviewer': 'volunteer-01',
            'reason': 'Compared original image', 'confirmed_w2': True,
            'corrections': {'1': '30000.00'}, 'tax_year': 2025,
        },
    },
}
graph.invoke(Command(resume=answer), case_config(case_id))
```

`corrections` contains only verified values. Missing/unreadable/ambiguous values require explicit correction; blank is not zero. `stop` rejects that extraction and halts the case. The existing six assignment conditions keep their original continue/stop policies. The human gate can now write `extracted` through the registered validation tool. Revision-aware merging prevents a stale pending record from replacing an approved record. Same-revision conflicts raise instead of silently selecting a value. Legacy test records without revisions keep the original reducer behavior.

## P4/P5: result contract

`extracted[doc_id]` contains `kind`, `fields`, `status`, `revision`, and complete `document` / `record` evidence. Each `fields['box_N']` contains exactly `value`, `formula`, `inputs`, `source`, `tool`. `source`, `formula` and `tool` are strings matching the supplied TypedDict. The full structured source is in `inputs.evidence`. Money is an exact decimal string; do not perform float arithmetic in the extraction agent.

`status == 'ready_for_rules'` means transcription was visually verified, **not** that the return is in scope. Inspect unstructured W-2 boxes 12–20. Do not use pending/rejected monetary records. The special `test_fixture` status is only for explicit offline synthetic text fixtures.

## P2: memory

Use the case ID as `thread_id`, the same SQLite DB path on every run, and a consistent graph schema. `src.memory.load_resume_context(graph, case_id)` reads existing state without running the graph. It returns a plain-language summary, pending question, status and waiting flag. The summary does not expose fact values or escalation reasons. Do not accept new chat input while waiting for a human.

`CaseMemory` remains available for detailed answer history and optimistic revision checks; see P2_QUICKSTART.md. That answer store is distinct from graph checkpoints. P2/P1 must reconcile revisions and invalidate stale downstream computations after edits.

## Context measurement

Actual extraction usage is captured by ToolBox and logged only by Runner as `token_source: openai_api_usage`. Other agents retain explicitly labelled estimates. Scoped workers receive only the current document and safety fields. When the graph is explicitly unscoped for benchmarking, P3 can include previous transcriptions, never previous images or API keys.

Run `python scripts/benchmark_context.py --compare` using the project environment. This measurement-only graph processes ten images sequentially in one thread per mode and makes 20 paid API calls. It writes real provider counts to `docs/metrics.md`. This is a controlled P3 context experiment, not a full six-agent accuracy evaluation. The production team path remains parallel. No real counts were fabricated.

## Remaining team work

- Replace Intake/Computation/Review stubs and verify the shared Rules assumptions.
- Connect the real taxpayer UI, document conflict claims and final return output.
- The provided Rules agent and human gate use different filing-status naming conventions in some paths; P1/P4 must reconcile them. P3 does not silently change eligibility behavior.
- W-2-only extraction is supported. Other document types route to human handling; this does not mean every such type is tax-out-of-scope under the assignment.
- Full team tests and live API accuracy must run in an environment with project dependencies and an API key.
