"""Run a scenario against the compiled graph: python -m scripts.run_scenarios clean"""
import argparse
import uuid

from src.graph import build_graph
from src.scenarios import clean_case

SCENARIOS = {"clean": clean_case}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario", choices=SCENARIOS)
    parser.add_argument("--no-context-strategy", action="store_true",
                        help="give every agent the full state (for measurement)")
    parser.add_argument("--trace-dir", default=None)
    args = parser.parse_args()

    graph = build_graph(trace_dir=args.trace_dir, context_strategy=not args.no_context_strategy)
    thread_id = f"{args.scenario}-{uuid.uuid4().hex[:8]}"
    result = graph.invoke(SCENARIOS[args.scenario](), {"configurable": {"thread_id": thread_id}})

    print(f"thread_id: {thread_id}")
    print(f"status:    {result['status']}")
    print("route:     " + " -> ".join(e["to"] for e in result["handoff_log"]))
    print(f"computed:  {sorted(result.get('computed', {}))}")
    print(f"trace:     {(args.trace_dir or 'traces')}/{thread_id}.jsonl")
    if result["status"] == "complete":
        print("DRAFT READY (nothing was filed)")


if __name__ == "__main__":
    main()
