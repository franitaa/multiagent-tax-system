"""The README diagram is generated from the compiled graph and must not go stale."""
from scripts import draw_graph


def test_readme_and_mmd_match_the_compiled_graph():
    diagram = draw_graph.render_mermaid()
    readme = draw_graph.README.read_text(encoding="utf-8")
    assert draw_graph.readme_with(diagram, readme) == readme, "run: python -m scripts.draw_graph"
    assert draw_graph.MERMAID_FILE.read_text(encoding="utf-8") == diagram


def test_diagram_is_hub_and_spoke():
    diagram = draw_graph.render_mermaid()
    for node in ("orchestrator", "human", "intake", "extraction", "rules", "computation", "review"):
        assert f"\t{node}(" in diagram or f"\t{node}([" in diagram
        if node != "orchestrator":
            assert f"{node} --> orchestrator;" in diagram  # every spoke returns to the hub
    assert "orchestrator -. &nbsp;end&nbsp; .-> __end__;" in diagram  # only the hub can end the run
