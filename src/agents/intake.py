"""STUB. Owned by the Intake teammate. Replace the body; keep the signature and the
state fields this agent is allowed to write (see src/orchestration/access.py)."""


def run(view, tools):
    user_turns = sum(1 for m in view.get("messages", []) if m["role"] == "user")
    if user_turns < 2:
        question = "STUB QUESTION: how old are you and what is your filing status?"
        return {
            "messages": [{"role": "assistant", "content": question}],
            "pending_question": question,
            "handoff_request": {"to": "end", "reason": "awaiting user reply"},
        }
    return {
        "facts": {
            "age": {"value": 70, "source": "user"},
            "filing_status_claim": {"value": "single", "source": "user"},
        },
        "pending_question": None,
        "intake_complete": True,
        "handoff_request": {"to": "extraction", "reason": "intake complete"},
    }
