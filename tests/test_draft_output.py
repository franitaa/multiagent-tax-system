"""A completed graph run writes a draft 1040-SR whose amounts each carry their provenance."""
import pytest

from src import state as S
from src.draft_form import write_draft_form
from src.graph import build_graph
from src.scenarios import clean_case
from tests.helpers import cfg


def test_a_clean_run_writes_a_draft_with_click_to_see_sources(tmp_path):
    result = build_graph(trace_dir=tmp_path).invoke(clean_case(), cfg("draft-1"))
    assert result["status"] == S.COMPLETE

    path = write_draft_form(result, tmp_path / "out", "draft-1")
    page = path.read_text(encoding="utf-8")
    assert path.name == "draft-1_1040sr.html" and "DRAFT, not filed" in page
    assert page.count("<details") >= len(result["computed"])  # every amount expands to its source
    assert "Formula" in page and "Tool" in page


def test_no_draft_is_written_without_computed_lines(tmp_path):
    with pytest.raises(ValueError):
        write_draft_form({"case_id": "x", "computed": {}}, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_no_draft_is_written_for_an_amount_without_provenance(tmp_path):
    with pytest.raises(ValueError):
        write_draft_form({"case_id": "x", "computed": {"line_9": {"value": 5}}}, tmp_path)
    assert list(tmp_path.iterdir()) == []
