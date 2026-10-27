"""Test-data scenarios shared by tests and scripts. Fake data only; no real SSNs."""


def user(text: str) -> dict:
    return {"role": "user", "content": text}


def document(doc_id: str = "doc-1", kind: str = "W-2") -> dict:
    return {"id": doc_id, "kind": kind, "text": "TEST DATA\nBox 1: 1000.00\nBox 2: 0.00",
            "fixture_format": "synthetic-w2-v1", "synthetic_confirmed": True}


def clean_case(case_id: str = "clean-1", turns: int = 2, n_docs: int = 1) -> dict:
    """In-scope single filer with one W-2. turns=2 answers intake in one call; turns=1
    makes the graph yield after Intake's first question."""
    messages = [user("Hi, I need help with my 2025 return.")]
    if turns >= 2:
        messages.append(user("I am 70, single, with one W-2."))
    return {
        "case_id": case_id,
        "messages": messages,
        "documents": [document(f"doc-{i + 1}") for i in range(n_docs)],
    }


# ---- escalation scenarios ------------------------------------------------------------
from src import state as S  # noqa: E402
from src.agents import AGENTS  # noqa: E402

# Which stub raises each condition, and a made-up reason (test data only).
CONDITION_SOURCES = {
    S.OUT_OF_SCOPE: ("rules", "TEST: return includes a Schedule C"),
    S.SOURCE_CONFLICT: ("rules", "TEST: user says $0 interest, document shows interest"),
    S.FORM_1099R_BOX_2B: ("extraction", "TEST: 1099-R box 2b 'taxable amount not determined' checked"),
    S.TAX_ADVICE_REQUEST: ("intake", "TEST: user asked whether they should itemize"),
    S.FILING_STATUS_AMBIGUITY: ("rules", "TEST: spouse died during the tax year"),
    S.EXPLOITATION_SIGNS: ("intake", "TEST: relative is pressuring the user to sign"),
}


def raising(base_run, agent: str, condition: str, reason: str, when=None):
    """Wrap a stub so it sets an escalation flag (once: not again after a human resolved it)."""

    def run(view, tools):
        update = dict(base_run(view, tools))
        resolved = {d["condition"] for d in view.get("human_decisions", [])}
        if condition not in resolved and (when is None or when(view)):
            update["escalation"] = {
                "pending": True, "condition": condition, "reason": reason, "raised_by": agent,
            }
        return update

    return run


def escalation_case(condition: str, when=None) -> dict:
    """Agent overrides (for build_graph(agents=...)) that raise `condition` in a clean case."""
    agent, reason = CONDITION_SOURCES[condition]
    return {agent: raising(AGENTS[agent], agent, condition, reason, when)}
