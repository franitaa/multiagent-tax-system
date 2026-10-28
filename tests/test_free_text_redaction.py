"""Escalation reasons and volunteer notes are free text. They go into graph state and checkpoints,
so identifiers in them are redacted at the runner, as the audit copy already is. Test data only."""
from langgraph.types import Command

from src.graph import build_graph
from src.orchestration.runner import Runner
from src.scenarios import spouse_died_case
from tests.helpers import cfg

LEAK = "Call 555-123-4567, mail pat@example.com, SSN 123-45-6789."


def assert_clean(text):
    assert "555-123-4567" not in text and "pat@example.com" not in text and "123-45-6789" not in text


def test_reasons_queued_reasons_and_notes_are_redacted():
    update = {"escalation": {"pending": True, "condition": "OUT_OF_SCOPE", "reason": LEAK,
                             "queued": [{"condition": "TAX_ADVICE_REQUEST", "reason": LEAK}]},
              "human_decisions": [{"decision": "continue", "note": LEAK, "reviewer": "Pat"}]}
    out = Runner._redact_free_text(update)
    assert_clean(out["escalation"]["reason"])
    assert_clean(out["escalation"]["queued"][0]["reason"])
    assert_clean(out["human_decisions"][0]["note"])
    assert out["escalation"]["condition"] == "OUT_OF_SCOPE" and out["human_decisions"][0]["reviewer"] == "Pat"
    assert update["escalation"]["reason"] == LEAK  # the caller's update is not modified


def test_practice_ssns_and_other_updates_pass_through_unchanged():
    update = {"escalation": {"pending": True, "condition": "OUT_OF_SCOPE", "reason": "practice 912-34-5678"},
              "status": "x", "human_decisions": []}
    assert Runner._redact_free_text(update) == update
    assert Runner._redact_free_text({"extracted": {}}) == {"extracted": {}}
    assert Runner._redact_free_text({"escalation": None}) == {"escalation": None}


def test_state_never_holds_the_identifiers_from_a_real_run(tmp_path):
    case, agents = spouse_died_case()
    original = agents["intake"]

    def leaky_intake(view, tools):
        update = original(view, tools)
        flag = update.get("escalation")
        if isinstance(flag, dict) and flag.get("reason"):
            update["escalation"] = {**flag, "reason": f"{flag['reason']} {LEAK}"}
        return update

    graph = build_graph(trace_dir=tmp_path, agents={**agents, "intake": leaky_intake})
    graph.invoke(case, cfg("free-text"))
    paused = graph.get_state(cfg("free-text")).values["escalation"]
    assert "[REDACTED SSN]" in paused["reason"]
    assert_clean(paused["reason"])

    result = graph.invoke(Command(resume={
        "decision": "continue", "note": f"Confirmed. {LEAK}",
        "resolution": {"filing_status": "married_filing_jointly"}}), cfg("free-text"))
    notes = [d["note"] for d in result["human_decisions"]]
    assert notes and all("Confirmed" in n for n in notes)
    for note in notes:
        assert_clean(note)
