"""What Extraction does with a document it cannot read (anything that is not a W-2).

Business rule 5: only the in-scope profile is handled, everything else goes to a human. The
in-scope forms are W-2, SSA-1099, 1099-R, 1099-INT and 1099-DIV. Only the W-2 is read today.
  * an unsupported kind (1099-NEC, Schedule C, a K-1, no kind at all): OUT_OF_SCOPE, stop-only;
  * a 1099-R: its box 2b decides whether the return is in scope and nothing here can read it, so
    it is escalated (FORM_1099R_BOX_2B), never waved through;
  * SSA-1099, 1099-INT, 1099-DIV: skipped with a reason. KNOWN GAP (issue #27):
    their amounts are not captured anywhere, because Intake only asks yes/no. Those tests pin the
    current behaviour so that changing it is a decision, not an accident.
"""
import pytest
from langgraph.types import Command

from src import state as S
from src.agents import extraction
from src.graph import build_graph
from src.scenarios import clean_case, document
from tests.helpers import cfg


def run(kind, doc_id="doc-9"):
    doc = document(doc_id, kind)
    return extraction.run({"documents": [doc]}, tools=None)


# ---- the agent --------------------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["1099-NEC", "Schedule C", "K-1", "W-2G", "", None, "  1099-nec "])
def test_an_unsupported_kind_is_escalated_out_of_scope(kind):
    update = run(kind)
    flag = update["escalation"]
    assert flag["pending"] and flag["condition"] == S.OUT_OF_SCOPE and flag["raised_by"] == "extraction"
    assert flag["document_id"] == "doc-9"
    record = update["extracted"]["doc-9"]
    assert record["status"] == "skipped" and record["fields"] == {}  # nothing was read
    assert update["handoff_request"]["to"] == "human"


@pytest.mark.parametrize("kind", ["1099-R", "1099r", " 1099-r "])
def test_a_1099r_is_escalated_because_box_2b_cannot_be_read(kind):
    update = run(kind)
    flag = update["escalation"]
    assert flag["pending"] and flag["condition"] == S.FORM_1099R_BOX_2B
    assert "2b" in flag["reason"] and update["extracted"]["doc-9"]["status"] == "skipped"
    assert update["handoff_request"]["to"] == "human"


def test_the_reason_never_echoes_a_long_or_odd_kind():
    flag = run("X" * 500 + "\n123-45-6789")["escalation"]
    assert len(flag["reason"]) <= 120 and "\n" not in flag["reason"] and "6789" not in flag["reason"]


@pytest.mark.parametrize("kind", ["SSA-1099", "1099-INT", "1099-DIV", "ssa-1099"])
def test_known_gap_in_scope_forms_are_skipped_without_amounts(kind):
    update = run(kind)
    assert "escalation" not in update
    record = update["extracted"]["doc-9"]
    assert record["status"] == "skipped" and record["fields"] == {}
    assert update["handoff_request"]["to"] == "rules"


# ---- through the graph --------------------------------------------------------------------------


def case_with(kind):
    case = clean_case()
    case["documents"] = [document("doc-1", kind)]
    return case


@pytest.mark.parametrize("kind, condition", [("1099-NEC", S.OUT_OF_SCOPE), ("1099-R", S.FORM_1099R_BOX_2B)])
def test_the_case_stops_for_a_volunteer_and_never_reaches_computation(tmp_path, kind, condition):
    graph = build_graph(trace_dir=tmp_path)
    result = graph.invoke(case_with(kind), cfg("t"))
    assert result["__interrupt__"][0].value["condition"] == condition
    assert result["__interrupt__"][0].value["options"] == ["stop"]  # a human cannot take this on
    values = graph.get_state(cfg("t")).values
    assert not values.get("computed") and values["status"] == S.AWAITING_HUMAN
    final = graph.invoke(Command(resume={"decision": "stop", "note": ""}), cfg("t"))
    assert final["status"] == S.HALTED_BY_HUMAN and not final.get("computed")
