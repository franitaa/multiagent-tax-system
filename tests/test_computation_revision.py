"""Computation acts on Review's send-back findings (view["pending_revision"]).

Two findings it can fix without guessing: a document amount that did not reach its line (text
such as "20000.00" is read as a number) and a tool that used the wrong filing status (use the
one in eligibility). Everything else is ignored, so a send-back it cannot fix changes nothing."""
from src import state as S
from src.agents import computation
from src.graph import build_graph
from src.orchestration.access import ToolBox
from src.scenarios import clean_case
from tests.helpers import cfg, text_amount_extraction

SOURCES = {"check": "sources", "line": "line_1a", "severity": "error",
           "issue": "doc-1 box_1 (20000.0) does not reach line_1a"}
STATUS = {"check": "recompute", "line": "line_12e", "severity": "error",
          "issue": "used filing status 'single', eligibility says 'married_filing_jointly'"}


def view(box_1="20000.00", findings=None, **extra):
    facts = {"taxpayer_birth_date": {"value": "1950-03-04", "source": "user"},
             "filing_status": {"value": "single", "source": "user"}}
    return {
        "facts": facts,
        "eligibility": {"filing_status": "married_filing_jointly"},
        "extracted": {"doc-1": {"doc_id": "doc-1", "kind": "W-2", "fields": {"box_1": {"value": box_1}}}},
        **({"pending_revision": {"target": "computation", "round": 1, "findings": findings}}
           if findings is not None else {}),
        **extra,
    }


def run(v):
    return computation.run(v, ToolBox("computation"))


def test_the_first_pass_does_not_use_a_text_amount():
    update = run(view())
    assert update["computed"]["line_1a"]["value"] == 0
    assert update["handoff_request"]["reason"] == "lines computed"


def test_a_sources_finding_makes_it_read_the_text_amount():
    update = run(view(findings=[SOURCES]))
    record = update["computed"]["line_1a"]
    assert record["value"] == 20000.0 and record["inputs"] == {"doc-1.box_1": 20000.0}
    assert "'20000.00' read as a number" in record["formula"] and record["source"].startswith("Document doc-1")
    assert update["computed"]["line_1z"]["value"] == 20000.0
    assert "read text amounts" in update["handoff_request"]["reason"]


def test_other_text_forms_are_read_and_junk_is_not():
    for text, value in (("$20,000.00", 20000.0), ("1,234", 1234.0), ("12,34", 0), ("about 20000", 0)):
        assert run(view(text, [SOURCES]))["computed"]["line_1a"]["value"] == value


def test_a_recompute_finding_about_filing_status_uses_the_status_in_eligibility():
    first = run(view())["computed"]["line_12e"]
    fixed = run(view(findings=[STATUS]))
    assert first["inputs"]["filing_status"] == "single"
    assert fixed["computed"]["line_12e"]["inputs"]["filing_status"] == "married_filing_jointly"
    assert fixed["computed"]["line_12e"]["value"] > first["value"]
    assert "filing status from eligibility" in fixed["handoff_request"]["reason"]


def test_a_volunteers_filing_status_is_never_replaced_by_the_one_in_eligibility():
    v = view(findings=[STATUS])
    v["facts"]["filing_status"] = {"value": "single", "source": "human:FILING_STATUS_AMBIGUITY"}
    assert run(v)["computed"]["line_12e"]["inputs"]["filing_status"] == "single"


def test_findings_it_cannot_fix_change_nothing():
    unfixable = [{"check": "scope", "line": None, "issue": "Rules has not decided eligibility"},
                 {"check": "completeness", "line": "line_9", "issue": "is required but missing"},
                 {"check": "recompute", "line": "line_16", "issue": "is 100, recomputed 90"},
                 {"line": "line_1a", "issue": "stub finding without a check"}, "not a finding"]
    assert run(view(findings=unfixable)) == run(view())


def test_a_text_taxable_amount_on_a_1099r_is_not_treated_as_undetermined():
    def pension(box_2a):
        v = view()
        v["extracted"]["doc-2"] = {"doc_id": "doc-2", "kind": "1099-R",
                                   "fields": {"box_1": {"value": 6000.0}, "box_2a": {"value": box_2a}}}
        return run(v)

    assert "escalation" not in pension("5000.00")
    assert pension(None)["escalation"]["condition"] == S.FORM_1099R_BOX_2B


def test_the_real_review_sends_text_amounts_back_and_the_second_pass_passes(tmp_path):
    graph = build_graph(trace_dir=tmp_path, agents={"extraction": text_amount_extraction})
    result = graph.invoke(clean_case(), cfg("revision-e2e"))
    route = [e["to"] for e in result["handoff_log"]]
    assert result["status"] == S.COMPLETE and route.count("computation") == 2
    assert result["revision_count"] == 1
    assert [f["check"] for f in result["review_history"][0]["findings"]] == ["sources"]
    assert result["computed"]["line_1a"]["value"] == 1000.0 and result["review"]["verdict"] == "pass"
