"""PRV-3: the draft 1040-SR shows every Assignment 7 section 3.1 item, and every amount expands to
how it was produced. Test data only."""
import pathlib
import re
import tempfile
from html.parser import HTMLParser

import pytest
from langgraph.types import Command

from scripts import render_case, render_draft
from src import state as S
from src.agents import computation
from src.draft_form import render_draft_html, write_draft_form
from src.graph import build_graph
from src.orchestration.access import ToolBox
from src.scenarios import clean_case, spouse_died_case
from tests.helpers import cfg, text_amount_extraction

_CHAT_PAGE = __import__('pathlib').Path(__file__).resolve().parents[1] / 'src' / 'ui' / 'taxpayer_chat.py'

# Every line in section 3.1 that Computation derives or reads.
SPEC_LINES = ["1z", "2a", "2b", "3a", "3b", "4a", "4b", "5a", "5b", "6a", "6b", "9", "10", "11a",
              "12e", "13b", "14", "15", "16", "24", "25a", "25b", "25d", "26", "33", "34", "37"]


def rich_view():
    view = dict(render_draft.sample_view)
    view["facts"] = {**view["facts"],
                     "adjustments_amount": {"value": 300, "source": "direct user input"}}
    view["extracted"] = {
        **view["extracted"],
        "doc-5": render_draft.doc("1099-R", box_1=6000, box_2a=5000, ira_sep_simple=True),
        "doc-6": render_draft.doc("1099-R", box_1=2000, box_2a=1500),
    }
    return view


@pytest.fixture(scope="module")
def rich_form():
    view = rich_view()
    computed = computation.run(view, ToolBox("computation"))["computed"]
    return render_draft_html(computed, view["facts"], {"filing_status": "single"}, case_id="rich"), computed


class Structure(HTMLParser):
    """Tags balance, and every <details> has exactly one <summary>."""

    VOID = {"meta", "br", "hr", "img", "input", "link"}

    def __init__(self):
        super().__init__()
        self.stack, self.problems, self.summaries = [], [], []

    def handle_starttag(self, tag, attrs):
        if tag not in self.VOID:
            self.stack.append(tag)
        if tag == "details":
            self.summaries.append(0)
        if tag == "summary" and self.summaries:
            self.summaries[-1] += 1

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        if not self.stack or self.stack[-1] != tag:
            self.problems.append(f"unexpected </{tag}> with {self.stack[-3:]} open")
        else:
            self.stack.pop()


class Elements(HTMLParser):
    """The real elements and attribute names in a page (escaped text is not an element)."""

    def __init__(self):
        super().__init__()
        self.tags, self.attributes = [], []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attributes += [name for name, _ in attrs]


def test_every_spec_line_is_on_the_form_with_its_own_source(rich_form):
    page, computed = rich_form
    for number in SPEC_LINES:
        assert f"<th scope='row'>{number}</th>" in page, f"line {number} is missing"
    assert page.count("<details>") == len(computed)  # one expandable source per amount
    for line, record in computed.items():
        assert f"<b>Formula:</b> {record['formula']}".replace("&", "&amp;") in page.replace("&#x27;", "'")


def test_every_amount_shows_formula_inputs_source_and_tool(rich_form):
    page, _ = rich_form
    blocks = re.findall(r"<details>.*?</details>", page, re.S)
    assert blocks and all(all(label in b for label in ("Formula:", "Inputs:", "Source:", "Tool:"))
                          for b in blocks)


def test_a_typed_in_amount_says_who_entered_it_and_when(rich_form):
    page, computed = rich_form
    record = computed["line_10"]
    assert "entered_by: taxpayer (via Intake)" in page and f"entered_on: {record['inputs']['entered_on']}" in page
    assert "Direct user input; no calculation performed" in page


def test_the_page_is_well_formed_and_accessible(rich_form):
    page, _ = rich_form
    parser = Structure()
    parser.feed(page)
    assert parser.problems == [] and parser.stack == []
    assert parser.summaries and set(parser.summaries) == {1}
    assert "<html lang='en'>" in page and page.count("<th scope='row'>") >= len(SPEC_LINES)
    assert "aria-label='Wages from Form(s) W-2: $28,000.00. Show how this was produced.'" in page
    for button in ("open-all", "close-all", "print"):
        assert f"id='{button}'" in page
    assert "beforeprint" in page  # every source opens before printing


def test_line_12d_lists_each_box_from_what_the_tool_was_given():
    view = rich_view()
    view["facts"]["filing_status"] = {"value": "married_filing_jointly", "source": "user"}
    view["facts"]["spouse_birth_date"] = {"value": "1950-01-01", "source": "user"}
    view["facts"]["spouse_blind"] = {"value": "yes", "source": "user"}
    computed = computation.run(view, ToolBox("computation"))["computed"]
    page = render_draft_html(computed, view["facts"], {"filing_status": "mfj"})
    rows = dict(re.findall(r"<tr><td>((?:You|Spouse)[^<]*)</td><td>([^<]*)</td></tr>", page))
    assert rows == {"You: born before January 2, 1961 (65 or older)": "Checked",
                    "You: blind": "Not checked",
                    "Spouse: born before January 2, 1961 (65 or older)": "Checked",
                    "Spouse: blind": "Checked"}
    assert "Boxes checked:</b> 3" in page


def test_dependents_show_name_relationship_and_a_masked_test_ssn_only(rich_form):
    page, _ = rich_form
    assert "Sample Grandchild" in page and "grandchild" in page
    assert "XXX-XX-5678" in page and "912-34-5678" not in page


def test_the_filing_status_says_who_set_it():
    computed = computation.run(rich_view(), ToolBox("computation"))["computed"]
    by_rules = render_draft_html(computed, {}, {"filing_status": "single"})
    assert "Single (from Eligibility &amp; Rules)" in by_rules
    override = {"filing_status": {"value": "head_of_household", "source": "human:FILING_STATUS_AMBIGUITY"}}
    assert "Head of household (from a volunteer&#x27;s decision)" in render_draft_html(computed, override, {})


def test_negative_amounts_read_naturally():
    page = render_draft_html({"line_11a": {"value": -5, "formula": "f", "inputs": {}, "source": "s", "tool": "t"}})
    assert ">-$5.00<" in page and "$-5" not in page


# ---- safety ------------------------------------------------------------------------------------


def test_nothing_from_a_document_or_answer_can_inject_markup():
    evil = "<script>alert(1)</script><img src=x onerror=alert(2)>"
    record = {"value": 1, "formula": evil, "inputs": {evil: evil}, "source": evil, "tool": evil}
    page = render_draft_html(
        {"line_9": record}, {"dependents": {"value": [{"name": evil, "relationship": evil, "ssn": evil}]}},
        {"filing_status": evil},
        review={"verdict": "fail", "findings": [{"check": evil, "line": evil, "issue": evil}]},
        review_history=[{"round": evil, "findings": [{"check": evil, "line": evil, "issue": evil}]}],
        decisions=[{"condition": evil, "decision": evil, "reviewer": evil, "note": evil}],
        case_id=evil)
    elements = Elements()
    elements.feed(page)
    assert elements.tags.count("script") == 1 and "img" not in elements.tags  # only our own script
    assert not [a for a in elements.attributes if a.startswith("on")]  # no event handlers
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page


def test_a_line_without_provenance_is_never_shown():
    with pytest.raises(ValueError, match="no provenance"):
        render_draft_html({"line_9": {"value": 5}})
    with pytest.raises(ValueError, match="no provenance record"):
        render_draft_html({"line_9": 5})


def test_volunteer_notes_are_redacted():
    page = render_draft_html(
        {"line_9": {"value": 1, "formula": "f", "inputs": {}, "source": "s", "tool": "t"}},
        decisions=[{"condition": "X", "decision": "continue", "note": "call 555-123-4567, SSN 123-45-6789"}])
    assert "555-123-4567" not in page and "123-45-6789" not in page


# ---- the audit record: review and volunteer decisions --------------------------------------------


def test_the_form_shows_the_review_send_back_that_fixed_the_draft(tmp_path):
    graph = build_graph(trace_dir=tmp_path, agents={"extraction": text_amount_extraction})
    state = graph.invoke(clean_case(), cfg("form-review"))
    page = render_draft_html(state["computed"], state["facts"], state["eligibility"], review=state["review"],
                             review_history=state["review_history"], decisions=state.get("human_decisions"))
    assert "<span class='ok'>Passed</span> after 1 send-back round to Computation" in page
    assert "sources on line_1a" in page and "Open findings" not in page


def test_a_failed_review_shows_its_open_findings():
    page = render_draft_html(
        {"line_9": {"value": 1, "formula": "f", "inputs": {}, "source": "s", "tool": "t"}},
        review={"verdict": "fail", "findings": [{"check": "totals", "line": "line_9", "issue": "is 1, recomputed 2"}]},
        review_history=[])
    assert "Did not pass" in page and "Open findings" in page and "totals on line_9: is 1, recomputed 2" in page


def test_the_hitl_case_shows_the_volunteer_who_decided(tmp_path):
    case, agents = spouse_died_case()
    graph = build_graph(trace_dir=tmp_path, agents=agents)
    graph.invoke(case, cfg("form-hitl"))
    state = graph.invoke(Command(resume={"decision": "continue", "note": "confirmed", "reviewer": "Pat Doe",
                                         "resolution": {"filing_status": "married_filing_jointly"}}),
                         cfg("form-hitl"))
    page = write_draft_form(state, tmp_path / "out", "hitl").read_text(encoding="utf-8")
    assert "Married filing jointly (from a volunteer&#x27;s decision)" in page
    assert "<td>FILING_STATUS_AMBIGUITY</td><td>continue</td><td>Pat Doe</td><td>confirmed</td>" in page


# ---- producing the files ----------------------------------------------------------------------------


def test_the_demo_forms_are_written_for_the_sample_and_both_eval_cases(tmp_path):
    paths = [render_draft.write_sample(tmp_path), *render_draft.write_eval_cases(tmp_path)]
    assert [p.name for p in paths] == ["sample_1040sr.html", "eval_case_1_1040sr.html", "eval_case_2_1040sr.html"]
    text = {p.name: p.read_text(encoding="utf-8") for p in paths}
    assert "Demo Volunteer" in text["eval_case_2_1040sr.html"]
    assert all("DRAFT, not filed" in t for t in text.values())


def test_render_case_writes_the_form_for_a_saved_case(tmp_path):
    from langgraph.checkpoint.sqlite import SqliteSaver

    runtime = tmp_path / "runtime"
    runtime.mkdir()
    with SqliteSaver.from_conn_string(str(runtime / "team_checkpoints.sqlite")) as saver:
        build_graph(saver, trace_dir=tmp_path / "t").invoke(clean_case("saved-1"), cfg("saved-1"))
    base = ["--runtime", str(runtime), "--output-dir", str(tmp_path / "out")]

    assert render_case.main(["saved-1", *base]) == 0
    page = (tmp_path / "out" / "saved-1_1040sr.html").read_text(encoding="utf-8")
    assert "case saved-1" in page and "<th scope='row'>1z</th>" in page
    from src.audit import AuditLog
    assert AuditLog(runtime / "traces" / "audit").read("saved-1")[-1]["event"] == "draft_form_written"


def test_render_case_refuses_an_unknown_case_and_a_bad_id(tmp_path, capsys):
    base = ["--runtime", str(tmp_path / "none"), "--output-dir", str(tmp_path / "out")]
    assert render_case.main(["nope", *base]) == 1 and "no saved case" in capsys.readouterr().err
    assert render_case.main(["../x", *base]) == 2
    assert not (tmp_path / "out").exists()


# ---- the taxpayer chat page ---------------------------------------------------------------------------


def chat_page(graph, case_id):
    import streamlit as st
    from streamlit.testing.v1 import AppTest

    from src.ui import chat_session

    original = chat_session.make_graph
    chat_session.make_graph = lambda *a, **k: graph
    st.cache_resource.clear()
    try:
        at = AppTest.from_file(str(_CHAT_PAGE), default_timeout=60)
        at.session_state["case_id"] = case_id
        return at.run()
    finally:
        chat_session.make_graph = original
        st.cache_resource.clear()


def test_the_finished_chat_page_shows_the_draft_form():
    from tests.interview import start_interview
    from tests.test_e2e_intake import graph_with_real_intake

    graph = graph_with_real_intake(pathlib.Path(tempfile.mkdtemp()))
    start_interview(graph, cfg("SF-123-456"))
    at = chat_page(graph, "SF-123-456")

    assert not at.exception
    assert [h.value for h in at.header if h.value == "Your draft tax form"]
    assert "Nothing has been filed" in " ".join(m.value for m in at.markdown)
    from src.ui import chat_session
    page = chat_session.draft_form_html(graph, "SF-123-456")
    assert page and "<th scope='row'>1z</th>" in page and "case SF-123-456" in page


def test_a_case_with_nothing_computed_has_no_form_and_the_page_says_so():
    from src.agents import intake_agent
    from src.ui import chat_session

    graph = build_graph(trace_dir=tempfile.mkdtemp(), agents={"intake": intake_agent.run})
    chat_session.start(graph, "SF-111-222")
    assert chat_session.draft_form_html(graph, "SF-111-222") is None
