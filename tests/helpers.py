import json


def cfg(thread_id):
    return {"configurable": {"thread_id": thread_id}}


def read_trace(trace_dir, thread_id):
    lines = (trace_dir / f"{thread_id}.jsonl").read_text().splitlines()
    return [json.loads(line) for line in lines]


def text_amount_extraction(view, tools):
    """An Extraction stand-in that reports box_1 as text ("1000.00"), the way an OCR-style
    extractor can. The real Extraction returns numbers, so tests about Review sending text
    amounts back to Computation must use this instead of whatever Extraction does today."""
    extracted = {
        doc["id"]: {"doc_id": doc["id"], "kind": doc["kind"],
                    "fields": {"box_1": {"value": "1000.00", "source": doc["id"]}}}
        for doc in view.get("documents", [])
    }
    return {"extracted": extracted, "handoff_request": {"to": "rules", "reason": "documents extracted"}}
