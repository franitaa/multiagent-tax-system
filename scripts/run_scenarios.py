"""Run a scenario against the compiled graph.

  python -m scripts.run_scenarios clean
  python -m scripts.run_scenarios interrupt [--condition TAX_ADVICE_REQUEST]
  python -m scripts.run_scenarios spouse-died [--filing-status married_filing_jointly]

`interrupt` raises one escalation and resumes with a decision that is valid for it
(continue for the three continuable conditions, stop for the others).
`spouse-died` is eval case 2: filing-status ambiguity, resumed with continue + note + filing status.
"""
import argparse
import sys
import uuid

from langgraph.types import Command

from src import state as S
from src.graph import build_graph
from src.orchestration.human import CONTINUABLE, FILING_STATUSES
from src.scenarios import CONDITION_SOURCES, clean_case, escalation_case, spouse_died_case


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario", choices=["clean", "interrupt", "spouse-died"])
    parser.add_argument("--no-context-strategy", action="store_true",
                        help="give every agent the full state (for measurement)")
    parser.add_argument("--trace-dir", default=None)
    parser.add_argument("--condition", default=S.TAX_ADVICE_REQUEST, choices=sorted(CONDITION_SOURCES),
                        help="interrupt scenario: which escalation the stub raises")
    parser.add_argument("--filing-status", default="married_filing_jointly", choices=FILING_STATUSES,
                        help="spouse-died scenario: the (demo) value the volunteer supplies")
    args = parser.parse_args()

    resume = None
    if args.scenario == "clean":
        case, agents = clean_case(), None
    elif args.scenario == "interrupt":
        case, agents = clean_case(), escalation_case(args.condition)
        if args.condition in CONTINUABLE:
            resume = {"decision": "continue", "note": "demo: reviewed with the taxpayer"}
        else:
            resume = {"decision": "stop", "note": "demo: this case cannot be handled here"}
    else:
        case, agents = spouse_died_case()
        resume = {
            "decision": "continue",
            "note": "demo: volunteer confirmed with the taxpayer that the spouse died in the tax year",
            "resolution": {"filing_status": args.filing_status},
        }

    graph = build_graph(trace_dir=args.trace_dir, context_strategy=not args.no_context_strategy,
                        agents=agents)
    thread_id = f"{args.scenario}-{uuid.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": thread_id}}
    result = graph.invoke(case, config)

    if "__interrupt__" in result:
        payload = result["__interrupt__"][0].value
        print(f"INTERRUPT ({payload['condition']}): paused for a human")
        print(f"  reason:  {payload['reason']}")
        print(f"  options: {payload['options']}")
        print(f"resuming with {resume}")
        result = graph.invoke(Command(resume=resume), config)
        if "__interrupt__" in result:
            print(f"ANSWER REJECTED: {result['__interrupt__'][0].value.get('error')}")
            return 1

    print(f"thread_id: {thread_id}")
    print(f"status:    {result['status']}")
    print("route:     " + " -> ".join(e["to"] for e in result["handoff_log"]))
    for d in result.get("human_decisions", []):
        print(f"human:     {d['condition']} -> {d['decision']} (note: {d['note']!r}, resolution: {d['resolution']})")
    if "filing_status" in result.get("facts", {}):
        fact = result["facts"]["filing_status"]
        print(f"filing status: {fact['value']} (source: {fact['source']}); "
              f"draft uses {result['eligibility']['filing_status']}")
    print(f"computed:  {sorted(result.get('computed', {}))}")
    print(f"trace:     {(args.trace_dir or 'traces')}/{thread_id}.jsonl")
    if result["status"] == S.COMPLETE:
        print("DRAFT READY (nothing was filed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
