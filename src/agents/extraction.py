"""STUB. Owned by the Document Extraction teammate."""


def run(view, tools):
    extracted = {
        doc["id"]: {
            "doc_id": doc["id"],
            "kind": doc["kind"],
            "fields": {"box_1": {"value": 1000.0, "source": doc["id"]}},  # stub test value
        }
        for doc in view.get("documents", [])
    }
    return {"extracted": extracted, "handoff_request": {"to": "rules", "reason": "documents extracted"}}
