# Validation and limitations

Authoring environment: Python 3.12 on Linux.

Executed:
- `python -m compileall -q silverfile-team-p3`: passed.
- `python -m unittest discover -s tests_p3 -v`: 57 tests discovered, 54 passed, 3 skipped.
- Passing tests cover image bytes, source hashes, team provenance shapes, correction history, revision-safe merges, credential exclusion from returned records, strict fixture parsing, durable intake memory and safe resume summaries.

Not executed here:
- Two actual LangGraph integration tests (restart/resume and parallel document approvals) were skipped because LangGraph was unavailable.
- One Streamlit startup test was skipped because Streamlit was unavailable.
- The supplied team's complete pytest suite could not be run because pytest/LangGraph were unavailable. Dependency installation was attempted but the environment could not obtain these packages.
- Live OpenAI extraction, token benchmark and Windows bootstrap were not executed; no user API key was provided.

The three skipped tests are real tests, not placeholders. Run `python -m pytest -q` in the installed project environment. A no-network mocked reader is injected for the image integration tests. Do not interpret mocked token counts or a passing fixture as live-model accuracy.

The supplied agents still contain stubs; even a passing team test does not produce a valid 1040-SR. The original six-condition escalation policy is retained, with an additional document-specific EXTRACTION_REVIEW condition. The root P5 computation helper is separate from the registered Computation stub and was not silently connected.

See test-results.txt for the exact executed P3 results. No fabricated API metrics are included.
