"""Write the draft 1040-SR for a saved case (PRV-3).

  python -m scripts.render_case SF-482-735
  python -m scripts.render_case SF-482-735 --runtime runtime --output-dir output

Reads the case's latest saved graph state (runtime/team_checkpoints.sqlite, the store the chat page
and the extraction workbench use) and writes <output-dir>/<case>_1040sr.html. Open it in a browser
and click any amount for its formula, inputs, source and tool. Nothing is filed, and a case with
nothing computed yet, or a line without provenance, gives an error instead of a form.
"""
import argparse
import sys
from pathlib import Path

from src.audit import AuditLog
from src.draft_form import write_draft_form
from src.retention import Layout, _case_id


def load_state(case_id: str, runtime="runtime") -> dict | None:
    """The case's latest saved state, or None if the case is unknown."""
    layout = Layout(runtime)
    if not layout.checkpoints.exists():
        return None
    from langgraph.checkpoint.sqlite import SqliteSaver

    with SqliteSaver.from_conn_string(str(layout.checkpoints)) as saver:
        found = saver.get_tuple({"configurable": {"thread_id": case_id}})
    return dict(found.checkpoint.get("channel_values", {})) if found else None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("case_id")
    parser.add_argument("--runtime", default="runtime")
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--actor", default="system:render_case", help="recorded in the audit log")
    args = parser.parse_args(argv)
    try:
        case_id = _case_id(args.case_id)
        state = load_state(case_id, args.runtime)
        if state is None:
            print(f"error: no saved case {case_id!r} under {args.runtime}", file=sys.stderr)
            return 1
        audit = AuditLog(Path(args.runtime) / "traces" / "audit")
        print(f"draft form: {write_draft_form(state, args.output_dir, case_id, audit=audit, actor=args.actor)}")
    except ValueError as problem:
        print(f"error: {problem}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
