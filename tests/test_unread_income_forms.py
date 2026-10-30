"""Issue #27: an in-scope SSA-1099, 1099-INT or 1099-DIV whose amounts were not read must not pass as
a complete draft. Computation says so in the source of the lines the form feeds, and the draft form
warns at the top of the page. Nothing is invented: the amount stays zero, nothing is escalated."""
import pytest

from src.agents import computation
from src.income_forms import unread_forms
from src.draft_form import render_draft_html, write_draft_form
from src.graph import build_graph
from src.orchestration.access import ToolBox
from src.scenarios import clean_case, document
from tests.helpers import cfg

NOT_READ = "NOT READ"


def skipped(kind, doc_id="doc-2"):
    """What Extraction leaves behind for an in-scope form it does not read."""
    return {doc_id: {"doc_id": doc_id, "kind": kind, "fields": {}, "status": "skipped"}}


def read(kind, doc_id="doc-2", **fields):
    return {doc_id: {"doc_id": doc_id, "kind": kind,
                     "fields": {k: {"value": v, "source": doc_id} for k, v in fields.items()}}}


def facts(**answers):
    base = {"filing_status": {"value": "single", "source": "user"}, "age": {"value": 70, "source": "user"}}
    return {**base, **{k: {"value": v, "source": "user"} for k, v in answers.items()}}


def run(extracted, **answers):
    update = computation.run({"facts": facts(**answers), "extracted": extracted, "eligibility": {}},
                             ToolBox("computation"))
    return update


# ---- which forms count as not read --------------------------------------------------------------


@pytest.mark.parametrize("kind, form, lines", [
    ("SSA-1099", "SSA-1099", ["line_6a", "line_25b"]),
    ("1099-INT", "1099-INT", ["line_2a", "line_2b", "line_25b"]),
    ("1099-DIV", "1099-DIV", ["line_3a", "line_3b", "line_25b"]),
])
def test_an_uploaded_form_with_no_amounts_is_listed_with_the_lines_it_feeds(kind, form, lines):
    assert unread_forms(facts(), skipped(kind)) == [{"form": form, "lines": lines}]


def test_saying_yes_to_a_form_with_no_document_counts_as_not_read():
    assert [f["form"] for f in unread_forms(facts(has_ssa_1099="yes"), {})] == ["SSA-1099"]
    assert unread_forms(facts(has_ssa_1099="no", has_1099_int="not_sure"), {}) == []


def test_a_form_with_any_amount_read_is_not_listed():
    assert unread_forms(facts(), read("SSA-1099", box_5=20000.0)) == []
    assert unread_forms(facts(has_1099_int="yes"), read("1099-INT", box_1=0.0)) == []


def test_text_amounts_count_as_read_only_once_the_send_back_allows_them():
    extracted = read("SSA-1099", box_5="20000.00")
    assert [f["form"] for f in unread_forms(facts(), extracted)] == ["SSA-1099"]
    assert unread_forms(facts(), extracted, read_text=True) == []


def test_a_w2_alone_lists_nothing():
    assert unread_forms(facts(has_w2="yes"), read("W-2", "doc-1", box_1=1000.0)) == []


# ---- Computation -------------------------------------------------------------------------------


def test_a_skipped_ssa_1099_says_so_instead_of_passing_as_a_plain_zero():
    update = run({**read("W-2", "doc-1", box_1=1000.0), **skipped("SSA-1099")})
    benefits, withheld = update["computed"]["line_6a"], update["computed"]["line_25b"]
    assert benefits["value"] == 0                       # nothing is made up
    assert NOT_READ in benefits["source"] and "SSA-1099" in benefits["source"]
    assert "No matching documents" not in benefits["source"]
    assert NOT_READ in withheld["source"] and "SSA-1099" in withheld["source"]
    assert update["handoff_request"]["to"] == "review" and "escalation" not in update


def test_lines_the_form_does_not_feed_are_unchanged():
    update = run(skipped("SSA-1099"))
    assert NOT_READ not in update["computed"]["line_2b"]["source"]
    assert update["computed"]["line_2b"]["source"] == "No matching documents; amount is zero"


def test_a_form_whose_amounts_were_read_gets_no_warning():
    update = run(read("SSA-1099", box_5=20000.0))
    assert update["computed"]["line_6a"]["value"] == 20000.0
    assert all(NOT_READ not in r["source"] for r in update["computed"].values())


def test_a_form_taxpayer_said_they_have_is_flagged_even_with_no_upload():
    update = run({}, has_1099_div="yes")
    assert NOT_READ in update["computed"]["line_3b"]["source"]
    assert NOT_READ not in update["computed"]["line_6a"]["source"]


def test_other_documents_on_the_same_line_keep_their_amounts():
    extracted = {**read("W-2", "doc-1", box_1=1000.0, box_2=100.0), **skipped("SSA-1099")}
    line = run(extracted)["computed"]["line_25b"]
    assert line["value"] == 0 and NOT_READ in line["source"]
    assert run(extracted)["computed"]["line_25a"]["value"] == 100.0


# ---- the draft form ----------------------------------------------------------------------------


def computed_for(extracted, **answers):
    return run(extracted, **answers)["computed"]


def test_the_form_warns_at_the_top_and_names_the_form_and_its_lines():
    extracted = skipped("SSA-1099")
    page = render_draft_html(computed_for(extracted), facts(), {}, extracted=extracted)
    assert "Income is missing from this draft" in page and "role='alert'" in page
    assert "SSA-1099: feeds lines 6a, 25b" in page
    assert page.index("Income is missing") < page.index("Filing status")


def test_the_form_has_no_warning_when_nothing_is_missing():
    extracted = read("W-2", "doc-1", box_1=1000.0)
    page = render_draft_html(computed_for(extracted), facts(), {}, extracted=extracted)
    assert "Income is missing" not in page


def test_the_form_without_extracted_state_behaves_as_before():
    assert "Income is missing" not in render_draft_html(computed_for({}), facts(), {})


def test_the_warning_uses_fixed_names_never_document_text():
    extracted = skipped("1099-INT")
    extracted["doc-2"]["kind"] = "1099-INT"
    extracted["doc-3"] = {"doc_id": "doc-3", "kind": "<script>alert(1)</script>", "fields": {}, "status": "skipped"}
    page = render_draft_html(computed_for(extracted), facts(), {}, extracted=extracted)
    assert "<script>alert(1)" not in page and "1099-INT: feeds lines 2a, 2b, 25b" in page


# ---- through the graph ---------------------------------------------------------------------------


def test_a_real_run_with_an_ssa_1099_writes_a_draft_that_warns(tmp_path):
    case = clean_case()
    case["documents"] = [document("doc-1", "W-2"), document("doc-2", "SSA-1099")]
    state = build_graph(trace_dir=tmp_path).invoke(case, cfg("unread-ssa"))
    assert state["status"] == "complete" and "__interrupt__" not in state
    assert NOT_READ in state["computed"]["line_6a"]["source"]
    page = write_draft_form(state, tmp_path / "out", "unread-ssa").read_text(encoding="utf-8")
    assert "Income is missing from this draft" in page and "SSA-1099: feeds lines 6a, 25b" in page


def test_a_clean_w2_run_has_no_warning(tmp_path):
    state = build_graph(trace_dir=tmp_path).invoke(clean_case(), cfg("clean-no-warning"))
    page = write_draft_form(state, tmp_path / "out", "clean").read_text(encoding="utf-8")
    assert "Income is missing" not in page
    assert NOT_READ not in "".join(r["source"] for r in state["computed"].values())


def test_the_draft_form_does_not_depend_on_an_agent_file():
    """The form shares `src/income_forms.py` with Computation; it must not import an agent."""
    import ast
    from pathlib import Path

    tree = ast.parse(Path("src/draft_form.py").read_text(encoding="utf-8"))
    imported = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module]
    imported += [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
    assert not [m for m in imported if m.startswith("src.agents")]
