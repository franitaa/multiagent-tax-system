"""Run a scenario against the compiled graph.

  python -m scripts.run_scenarios clean
  python -m scripts.run_scenarios interrupt [--condition TAX_ADVICE_REQUEST] [--decision continue|stop]
"""
import argparse
import uuid

from langgraph.types import Command

from src import state as S
from src.graph import build_graph
from src.scenarios import CONDITION_SOURCES, clean_case, escalation_case

SCENARIOS = {"clean": clean_case, "interrupt": clean_case}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario", choices=SCENARIOS)
    parser.add_argument("--no-context-strategy", action="store_true",
                        help="give every agent the full state (for measurement)")
    parser.add_argument("--trace-dir", default=None)
    parser.add_argument("--condition", default=S.EXPLOITATION_SIGNS, choices=sorted(CONDITION_SOURCES),
                        help="interrupt scenario: which escalation the stub raises")
    parser.add_argument("--decision", default="continue", choices=["continue", "stop"],
                        help="interrupt scenario: the human's decision on resume")
    args = parser.parse_args()

    agents = escalation_case(args.condition) if args.scenario == "interrupt" else None
    graph = build_graph(trace_dir=args.trace_dir, context_strategy=not args.no_context_strategy,
                        agents=agents)
    thread_id = f"{args.scenario}-{uuid.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": thread_id}}
    result = graph.invoke(SCENARIOS[args.scenario](), config)

    if "__interrupt__" in result:
        payload = result["__interrupt__"][0].value
        print(f"INTERRUPT: graph paused for a human -> {payload}")
        print(f"resuming with decision={args.decision!r}")
        result = graph.invoke(
            Command(resume={"decision": args.decision, "note": "demo decision"}), config
        )

    print(f"thread_id: {thread_id}")
    print(f"status:    {result['status']}")
    print("route:     " + " -> ".join(e["to"] for e in result["handoff_log"]))
    print(f"computed:  {sorted(result.get('computed', {}))}")
    print(f"trace:     {(args.trace_dir or 'traces')}/{thread_id}.jsonl")
    if result["status"] == "complete":
        print("DRAFT READY (nothing was filed)")


if __name__ == "__main__":
    main()
