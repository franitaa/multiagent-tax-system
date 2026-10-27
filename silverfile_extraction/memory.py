"""Conflict-detecting reducers for concurrent document workers. Prompts live in vision.py."""

def merge_versioned(left: dict | None, right: dict | None) -> dict:
    """Commutative record reducer: reject conflicting writes at the same revision."""
    merged = dict(left or {})
    for key, incoming in (right or {}).items():
        old = merged.get(key)
        if old is None or incoming["revision"] > old["revision"]:
            merged[key] = incoming
        elif incoming["revision"] == old["revision"] and incoming != old:
            raise ValueError("Conflicting writes for the same document revision.")
    return dict(sorted(merged.items()))


def merge_documents(left: dict | None, right: dict | None) -> dict:
    merged = dict(left or {})
    for key, value in (right or {}).items():
        if key in merged and merged[key] != value:
            raise ValueError("Document evidence is immutable; use a new document for a replacement.")
        merged[key] = value
    return dict(sorted(merged.items()))

