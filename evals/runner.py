"""Run the eval cases in evals/cases.json through the compiled graph and check each outcome.

  python -m evals.runner                 # every case, a table of results
  python -m evals.runner --case clean-single-w2
  python -m evals.runner --real-agents   # ignore the stand-ins (once every agent is real)

A case may give the `facts` Intake would record and the box `fields` Extraction would read.
By default those replace the Intake and Extraction agents for that case (stand-ins), so the
cases test Rules, Computation, Review and the orchestrator on known inputs. --real-agents
runs the agents on main instead.

A case marked `pending` describes behaviour that is not built yet. It is reported as PENDING
while it fails and as FIXED once it passes (then remove the marker). Only FAIL, a case that
should pass and does not, makes the exit code non-zero.
"""
import argparse
import json
import sys
import tempfile
import uuid
from pathlib import Path

from langgraph.types import Command

from src.graph import build_graph

CASES_FILE = Path(__file__).with_name("cases.json")
MAX_INTERRUPTS = 5

PASS, FAIL, PENDING, FIXED = "PASS", "FAIL", "PENDING", "FIXED"


def load_cases(path: Path = CASES_FILE) -> list[dict]:
    return json.loads(path.read_text())["cases"]


def _document_text(doc: dict) -> str:
    boxes = ", ".join(f"{box}: {value}" for box, value in doc.get("fields", {}).items())
    return f"TEST DATA {doc['kind']} {doc['id']}: {boxes}"


def graph_input(case: dict) -> dict:
    return {
        "case_id": case["id"],
        "messages": [{"role": "user", "content": text} for text in case["messages"]],
        "documents": [{"id": d["id"], "kind": d["kind"], "text": _document_text(d)}
                      for d in case.get("documents", [])],
    }


def stand_ins(case: dict) -> dict:
    """Agents that return exactly what the case says Intake and Extraction would produce."""
    agents = {}
    if "facts" in case:
        facts = {name: {"value": value, "source": "user"} for name, value in case["facts"].items()}

        def intake(view, tools):
            return {"facts": facts, "pending_question": None, "intake_complete": True,
                    "handoff_request": {"to": "extraction", "reason": "eval stand-in: answers given"}}

        agents["intake"] = intake
    if any("fields" in d for d in case.get("documents", [])):
        extracted = {
            d["id"]: {
                "doc_id": d["id"],
                "kind": d["kind"],
                "fields": {box: {"value": value, "source": f"{d['id']}.{box}"}
                           for box, value in d.get("fields", {}).items()},
            }
            for d in case["documents"]
        }

        def extraction(view, tools):
            return {"extracted": extracted,
                    "handoff_request": {"to": "rules", "reason": "eval stand-in: boxes given"}}

        agents["extraction"] = extraction
    return agents


def run_case(case: dict, *, real_agents: bool = False, trace_dir=None) -> dict:
    """Run one case. Returns the final state, the interrupts seen, and any error."""
    trace_dir = trace_dir or tempfile.mkdtemp(prefix="evals-")
    graph = build_graph(trace_dir=trace_dir, agents=None if real_agents else stand_ins(case))
    config = {"configurable": {"thread_id": f"eval-{case['id']}-{uuid.uuid4().hex[:6]}"}}
    answers = list(case.get("resume", []))
    interrupts: list[str] = []

    result = graph.invoke(graph_input(case), config)
    while "__interrupt__" in result:
        payload = result["__interrupt__"][0].value
        if payload.get("error"):
            return {"state": result, "interrupts": interrupts,
                    "error": f"the human gate rejected the answer: {payload['error']}"}
        interrupts.append(payload["condition"])
        if not answers or len(interrupts) > MAX_INTERRUPTS:
            return {"state": result, "interrupts": interrupts,
                    "error": f"paused for {payload['condition']} with no answer left in the case"}
        result = graph.invoke(Command(resume=answers.pop(0)), config)
    return {"state": result, "interrupts": interrupts, "error": None}


def check(case: dict, outcome: dict) -> list[str]:
    """Compare an outcome with the case's `expect`. Returns the problems found (empty = pass)."""
    expect, state = case["expect"], outcome["state"]
    problems = [outcome["error"]] if outcome["error"] else []

    if "interrupts" in expect and outcome["interrupts"] != expect["interrupts"]:
        problems.append(f"interrupts {outcome['interrupts']}, expected {expect['interrupts']}")
    if "status" in expect and state.get("status") != expect["status"]:
        problems.append(f"status {state.get('status')!r}, expected {expect['status']!r}")
    if "route_starts_with" in expect:
        route = [hop["to"] for hop in state.get("handoff_log", [])]
        if route[:len(expect["route_starts_with"])] != expect["route_starts_with"]:
            problems.append(f"route {route}, expected it to start with {expect['route_starts_with']}")
    eligibility = state.get("eligibility") or {}
    for name, value in expect.get("eligibility", {}).items():
        if eligibility.get(name) != value:
            problems.append(f"eligibility.{name} is {eligibility.get(name)!r}, expected {value!r}")
    for rule in expect.get("rules_include", []):
        if rule not in eligibility.get("applicable_rules", []):
            problems.append(f"rule {rule!r} not applied")
    computed = state.get("computed") or {}
    for line, value in expect.get("lines", {}).items():
        got = (computed.get(line) or {}).get("value")
        if got is None or abs(float(got) - value) > 0.5:
            problems.append(f"{line} is {got!r}, expected {value}")
    if expect.get("no_computed_lines") and computed:
        problems.append(f"lines were computed for a case that should stop first: {sorted(computed)}")
    if "review_verdict" in expect:
        verdict = (state.get("review") or {}).get("verdict")
        if verdict != expect["review_verdict"]:
            problems.append(f"review verdict {verdict!r}, expected {expect['review_verdict']!r}")
    if "human_decisions" in expect:
        got = [f"{d['condition']}:{d['decision']}" for d in state.get("human_decisions", [])]
        if got != expect["human_decisions"]:
            problems.append(f"human decisions {got}, expected {expect['human_decisions']}")
    return problems


def evaluate(case: dict, *, real_agents: bool = False, trace_dir=None) -> dict:
    try:
        problems = check(case, run_case(case, real_agents=real_agents, trace_dir=trace_dir))
    except Exception as exc:  # a crash is a result to report, not a reason to stop the suite
        problems = [f"crashed: {type(exc).__name__}: {exc}"]
    if case.get("pending"):
        result = FIXED if not problems else PENDING
    else:
        result = PASS if not problems else FAIL
    return {"id": case["id"], "title": case["title"], "result": result,
            "problems": problems, "pending": case.get("pending")}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", action="append", help="run only this case id (repeatable)")
    parser.add_argument("--real-agents", action="store_true",
                        help="ignore the stand-in Intake and Extraction answers")
    parser.add_argument("--trace-dir", default=None)
    parser.add_argument("--json", metavar="PATH", help="also write the results as JSON")
    args = parser.parse_args(argv)

    cases = load_cases()
    if args.case:
        unknown = set(args.case) - {c["id"] for c in cases}
        if unknown:
            parser.error(f"unknown case id(s): {sorted(unknown)}")
        cases = [c for c in cases if c["id"] in args.case]

    results = [evaluate(c, real_agents=args.real_agents, trace_dir=args.trace_dir) for c in cases]
    width = max(len(r["id"]) for r in results)
    for r in results:
        print(f"{r['result']:<8} {r['id']:<{width}}  {r['title']}")
        if r["result"] in (FAIL, PENDING):
            for problem in r["problems"]:
                print(f"{'':<8} {'':<{width}}    - {problem}")
        if r["result"] == PENDING:
            print(f"{'':<8} {'':<{width}}    (pending: {r['pending']})")
        if r["result"] == FIXED:
            print(f"{'':<8} {'':<{width}}    now passes: remove its 'pending' marker")

    counts = {k: sum(r["result"] == k for r in results) for k in (PASS, FAIL, PENDING, FIXED)}
    print("\n" + ", ".join(f"{n} {k.lower()}" for k, n in counts.items()) + f" (of {len(results)})")
    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=2))
    return 1 if counts[FAIL] else 0


if __name__ == "__main__":
    sys.exit(main())
