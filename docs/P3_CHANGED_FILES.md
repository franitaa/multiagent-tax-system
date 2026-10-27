# Changes relative to the supplied team ZIP

## Shared files for P1 review

- `src/graph.py`
- `src/orchestration/access.py`
- `src/orchestration/human.py`
- `src/orchestration/runner.py`
- `src/scenarios.py`
- `src/state.py`

## P3-owned additions and replacement

- `src/agents/extraction.py`: real tool-backed W-2 extraction agent.
- `src/p3/bridge.py`: image store, tool implementation, provenance adapter and human validation.
- `src/p3/service.py`: persistent team-graph workbench facade.
- `src/memory.py`: P1/P2 checkpointer and resume helpers.
- `silverfile_extraction/`: existing P3 extraction/memory core, retained for compatibility.
- `app.py`, `start.py`, `START_WINDOWS.cmd`: local integration UI and bootstrap.
- `tests_p3/`: core/adapter tests and dependency-enabled graph/UI checks.
- `scripts/benchmark_context.py`: real API context measurement.
- `data/`, `examples/`, `docs/`: fixtures, demos and integration instructions.
- `pyproject.toml`, `requirements.txt`, `.gitignore`, `.env.example`, `pytest.ini`, `.github/workflows/p3-tests.yml`: dependency, test and local-data handling setup.

All supplied agents other than Extraction were preserved byte-for-byte. No commit or push was performed. The supplied six-condition tests were not rewritten to hide failures. `src/scenarios.py` now contains explicit synthetic amounts so the new extractor no longer invents a value from a generic TEST DATA label.

The compiled graph is still P1's graph, with additional tool registry injection and safety context in scoped parallel workers. The new human review condition requires the corresponding policy/state/gate changes together; do not copy only extraction.py.
