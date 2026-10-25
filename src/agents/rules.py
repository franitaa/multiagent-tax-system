"""STUB. Owned by the Eligibility & Rules teammate."""


def run(view, tools):
    return {
        "eligibility": {
            "in_scope": True,
            "filing_status": "single",
            "citations": ["STUB: policy corpus citation"],
        },
        "handoff_request": {"to": "computation", "reason": "in scope; status determined"},
    }
