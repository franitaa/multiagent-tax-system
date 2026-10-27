"""Two-process MEM-1 acceptance check; this is not the full six-agent graph."""
import argparse
import json
import sys
from pathlib import Path
from typing import TypedDict

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from langgraph.graph import START, END, StateGraph
from langgraph.types import interrupt, Command
from silverfile_extraction.checkpointer import case_config, sqlite_checkpointer


class State(TypedDict, total=False):
    answer: str


def ask(state):
    return {"answer": interrupt({"question_id": "Q1", "question": "Were you married?"})}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["pause", "resume", "show"])
    parser.add_argument("--db", default="runtime/checkpointer-demo.sqlite")
    parser.add_argument("--case", default="MEM1-DEMO")
    args = parser.parse_args()
    builder = StateGraph(State)
    builder.add_node("ask", ask)
    builder.add_edge(START, "ask")
    builder.add_edge("ask", END)
    with sqlite_checkpointer(args.db) as saver:
        graph = builder.compile(checkpointer=saver)
        config = case_config(args.case)
        if args.phase == "pause":
            if graph.get_state(config).values or graph.get_state(config).next:
                raise ValueError("This case already exists. Use a different --case for a new test.")
            graph.invoke({}, config)
        elif args.phase == "resume":
            if not graph.get_state(config).next:
                raise ValueError("Run the pause phase first for the same case and database.")
            graph.invoke(Command(resume="yes"), config)
        snapshot = graph.get_state(config)
        print(json.dumps({"case_id": args.case, "pending": bool(snapshot.next), "state": snapshot.values}))


if __name__ == "__main__":
    main()

