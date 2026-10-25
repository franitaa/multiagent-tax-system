"""STUB. Owned by the Review/Audit teammate. Reviews and reports findings; never fixes."""


def run(view, tools):
    return {
        "review": {"verdict": "pass", "findings": [], "send_back_to": None},
        "handoff_request": {"to": "end", "reason": "no findings"},
    }
