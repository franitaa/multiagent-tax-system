import json


def cfg(thread_id):
    return {"configurable": {"thread_id": thread_id}}


def read_trace(trace_dir, thread_id):
    lines = (trace_dir / f"{thread_id}.jsonl").read_text().splitlines()
    return [json.loads(line) for line in lines]
