"""The metrics script runs both modes and writes a readable report."""
import sys

from scripts import measure_context


def test_metrics_script_output_matches_what_a_fresh_run_produces(tmp_path):
    out = tmp_path / "metrics.md"
    argv = sys.argv
    sys.argv = ["measure_context", "--turns", "8", "--docs", "3", "--out", str(out)]
    try:
        measure_context.main()
    finally:
        sys.argv = argv
    text = out.read_text()
    assert "estimates" in text.lower() and "| Total input tokens, all model calls |" in text
    assert text.count("| intake turn ") == 8
