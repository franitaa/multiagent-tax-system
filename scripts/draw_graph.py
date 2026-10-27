"""Generate the graph diagram from the compiled graph.

  python -m scripts.draw_graph          # rewrite docs/graph.mmd and the README block
  python -m scripts.draw_graph --check  # exit 1 if either is out of date

The README block sits between <!-- graph:start --> and <!-- graph:end -->.
"""
import argparse
import re
import sys
import tempfile
from pathlib import Path

from src.graph import build_graph

README = Path("README.md")
MERMAID_FILE = Path("docs/graph.mmd")
BLOCK = re.compile(r"(<!-- graph:start -->\n).*?(<!-- graph:end -->)", re.S)


def render_mermaid() -> str:
    with tempfile.TemporaryDirectory() as trace_dir:
        return build_graph(trace_dir=trace_dir).get_graph().draw_mermaid().strip() + "\n"


def readme_with(diagram: str, readme: str) -> str:
    return BLOCK.sub(lambda m: f"{m.group(1)}```mermaid\n{diagram}```\n{m.group(2)}", readme, count=1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    diagram = render_mermaid()
    new_readme = readme_with(diagram, README.read_text(encoding="utf-8"))
    stale = (not MERMAID_FILE.exists() or MERMAID_FILE.read_text(encoding="utf-8") != diagram
             or new_readme != README.read_text(encoding="utf-8"))
    if args.check:
        print("diagram is out of date: run python -m scripts.draw_graph" if stale else "diagram is up to date")
        return 1 if stale else 0
    MERMAID_FILE.write_text(diagram, encoding="utf-8")
    README.write_text(new_readme, encoding="utf-8")
    print(f"wrote {MERMAID_FILE} and updated {README}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
