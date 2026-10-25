"""STUB. Owned by the Computation teammate. Real numbers must come from deterministic
tool calls via `tools.call(...)`, each with a ProvenanceRecord."""


def run(view, tools):
    return {
        "computed": {
            "line_1a": {
                "value": 1000.0,
                "formula": "STUB: sum of box_1",
                "inputs": {"doc-1.box_1": 1000.0},
                "source": "doc-1",
                "tool": "stub_tool",
            }
        },
        "handoff_request": {"to": "review", "reason": "lines computed"},
    }
