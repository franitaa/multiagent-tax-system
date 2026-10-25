"""Test-data scenarios shared by tests and scripts. Fake data only; no real SSNs."""


def user(text: str) -> dict:
    return {"role": "user", "content": text}


def document(doc_id: str = "doc-1", kind: str = "W-2") -> dict:
    return {"id": doc_id, "kind": kind, "text": f"TEST DATA {kind} for {doc_id}"}


def clean_case(case_id: str = "clean-1", turns: int = 2) -> dict:
    """In-scope single filer with one W-2. turns=2 answers intake in one call; turns=1
    makes the graph yield after Intake's first question."""
    messages = [user("Hi, I need help with my 2025 return.")]
    if turns >= 2:
        messages.append(user("I am 70, single, with one W-2."))
    return {"case_id": case_id, "messages": messages, "documents": [document()]}
