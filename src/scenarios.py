"""Test-data scenarios shared by tests and scripts. Fake data only; no real SSNs."""


def user(text: str) -> dict:
    return {"role": "user", "content": text}


def document(doc_id: str = "doc-1", kind: str = "W-2") -> dict:
    return {"id": doc_id, "kind": kind, "text": f"TEST DATA {kind} for {doc_id}"}


def clean_case(case_id: str = "clean-1", turns: int = 2, n_docs: int = 1) -> dict:
    """In-scope single filer with one W-2. turns=2 answers intake in one call; turns=1
    makes the graph yield after Intake's first question."""
    messages = [user("Hi, I need help with my 2025 return.")]
    if turns >= 2:
        messages.append(user("I am 70, single, with one W-2."))
    return {
        "case_id": case_id,
        "messages": messages,
        "documents": [document(f"doc-{i + 1}") for i in range(n_docs)],
    }


# ---- escalation scenarios ------------------------------------------------------------
from src import state as S  # noqa: E402
from src.agents import AGENTS  # noqa: E402

# Which stub raises each condition, and a made-up reason (test data only).
CONDITION_SOURCES = {
    S.OUT_OF_SCOPE: ("rules", "TEST: return includes a Schedule C"),
    S.SOURCE_CONFLICT: ("rules", "TEST: user says $0 interest, document shows interest"),
    S.FORM_1099R_BOX_2B: ("extraction", "TEST: 1099-R box 2b 'taxable amount not determined' checked"),
    S.TAX_ADVICE_REQUEST: ("intake", "TEST: user asked whether they should itemize"),
    S.FILING_STATUS_AMBIGUITY: ("rules", "TEST: spouse died during the tax year"),
    S.EXPLOITATION_SIGNS: ("intake", "TEST: relative is pressuring the user to sign"),
}


def raising(base_run, agent: str, condition: str, reason: str, when=None):
    """Wrap a stub so it sets an escalation flag (once: not again after a human resolved it)."""

    def run(view, tools):
        update = dict(base_run(view, tools))
        resolved = {d["condition"] for d in view.get("human_decisions", [])}
        if condition not in resolved and (when is None or when(view)):
            update["escalation"] = {
                "pending": True, "condition": condition, "reason": reason, "raised_by": agent,
            }
        return update

    return run


def escalation_case(condition: str, when=None) -> dict:
    """Agent overrides (for build_graph(agents=...)) that raise `condition` in a clean case."""
    agent, reason = CONDITION_SOURCES[condition]
    return {agent: raising(AGENTS[agent], agent, condition, reason, when)}


def spouse_died_case(case_id: str = "spouse-died-1") -> tuple[dict, dict]:
    """Eval case 2: the taxpayer says their spouse died during the tax year, so the filing
    status is ambiguous. Returns (graph input, agent overrides). Intake raises the flag."""
    case = {
        "case_id": case_id,
        "messages": [
            user("Hi, I need help with my 2025 return."),
            user("My husband passed away in March, and I am not sure how to file."),
        ],
        "documents": [document()],
    }
    reason = "TEST: taxpayer says their spouse died during the tax year"
    agents = {"intake": raising(AGENTS["intake"], "intake", S.FILING_STATUS_AMBIGUITY, reason)}
    return case, agents


# ---- long session (context measurement) -------------------------------------------------

_ANSWERS = (
    "I worked part of the year and also helped my daughter with some bills, so I kept all of the "
    "envelopes that came in the mail and I am not sure which of them matter for the return.",
    "My pension payments started in the spring and my social security letter came in January, I "
    "put them in the green folder along with the bank statements the volunteer asked about.",
    "I live in the same house as last year and nothing about my address or my health insurance "
    "changed, although I did get a new phone number and I would like the letters sent by mail.",
    "I did not sell anything this year and I have no other accounts besides the savings account "
    "at the credit union, which sends me one statement every three months in the post.",
    "Last year a neighbour helped me fill in the paperwork and I think we used the same forms, but "
    "I no longer have the copy so I am going from memory about what we reported then.",
    "I received a few small payments from a company I used to work for and a letter about them, I "
    "can read it out if that helps, but I do not understand most of the boxes on it.",
)
_QUESTIONS = (
    "Thank you. Could you tell me a little more about that, in your own words?",
    "Understood. Is there anything about this you would like me to note for the volunteer?",
    "Got it. Which documents do you have in front of you at the moment?",
)


def long_answer(turn: int) -> str:
    """Deterministic test text of realistic length (about 45 words), no real data."""
    return f"(turn {turn}) " + _ANSWERS[turn % len(_ANSWERS)]


def long_document(doc_id: str, kind: str = "W-2") -> dict:
    """A document with a few KB of fake text, as a scanned page would be."""
    lines = (f"TEST DATA {kind} {doc_id} line {j}: box value placeholder, employer name placeholder, "
             f"period placeholder" for j in range(40))
    return {"id": doc_id, "kind": kind, "text": "\n".join(lines)}


def long_intake(turns: int):
    """Stub Intake for a long conversation. It remembers each answer as a structured fact
    (`answer_N`) and counts turns from those facts, so it works whether or not older chat
    messages are in its view. Complete after `turns` user messages."""

    def run(view, tools):
        answered = sum(1 for name in view.get("facts", {}) if name.startswith("answer_"))
        latest = view["messages"][-1]["content"]
        update = {"facts": {f"answer_{answered + 1}": {"value": latest[:60], "source": "user"}}}
        if answered + 1 >= turns:
            return {**update, "pending_question": None, "intake_complete": True,
                    "handoff_request": {"to": "extraction", "reason": "intake complete"}}
        question = _QUESTIONS[answered % len(_QUESTIONS)]
        return {**update, "messages": [{"role": "assistant", "content": question}],
                "pending_question": question,
                "handoff_request": {"to": "end", "reason": "awaiting user reply"}}

    return run


def revising_agents():
    """Review fails the first draft; Computation's revision (it sees pending_revision) passes."""
    base = AGENTS["computation"]

    def computation(view, tools):
        update = base(view, tools)
        if view.get("pending_revision"):
            update["computed"] = {"line_1a": {**update["computed"]["line_1a"], "formula": "STUB: revised"}}
        return update

    def review(view, tools):
        revised = view["computed"]["line_1a"]["formula"] == "STUB: revised"
        return {
            "review": {"verdict": "pass" if revised else "fail",
                       "findings": [] if revised else [{"line": "line_1a", "issue": "STUB finding"}],
                       "send_back_to": None if revised else "computation"},
            "handoff_request": {"to": "end" if revised else "computation", "reason": "stub review"},
        }

    return {"computation": computation, "review": review}


def run_long_session(graph, thread_id: str, turns: int = 30, n_docs: int = 12) -> dict:
    """Drive the long scenario one user message per graph call (as a UI would) and return the
    final state. Same input for any graph, so scoped and full modes can be compared."""
    config = {"configurable": {"thread_id": thread_id}}
    result = graph.invoke({
        "case_id": f"long-{turns}x{n_docs}",
        "messages": [user(long_answer(1))],
        "documents": [long_document(f"doc-{i + 1}") for i in range(n_docs)],
    }, config)
    for turn in range(2, turns + 1):
        assert result["status"] == "awaiting_user", result["status"]
        result = graph.invoke({"messages": [user(long_answer(turn))]}, config)
    return result


def decided_rules(view, tools):
    """Scenario-owned stand-in for Rules: always returns a decided, in-scope verdict. The long
    session is about context size, not eligibility, so it must not depend on the real Rules agent
    (which is being reworked and cannot decide from the long scenario's made-up facts)."""
    return {
        "eligibility": {"in_scope": True, "eligible_1040sr": True, "filing_status": "single",
                        "taxpayer_qualifies": True, "age_blindness_boxes": 1,
                        "citations": ["STUB: policy citation"]},
        "handoff_request": {"to": "computation", "reason": "in scope; status determined"},
    }


def text_extraction(view, tools):
    """Scenario-owned stand-in for Document Extraction: the real one reads W-2 images only, and
    this scenario's documents are plain-text test pages. One document per parallel worker."""
    return {
        "extracted": {
            doc["id"]: {"doc_id": doc["id"], "kind": doc["kind"],
                        "fields": {"box_1": {"value": 1000.0, "source": doc["id"]}}}
            for doc in view.get("documents", [])
        },
        "handoff_request": {"to": "rules", "reason": "documents extracted"},
    }


def long_session_agents(turns: int = 30) -> dict:
    return {"intake": long_intake(turns), "extraction": text_extraction, "rules": decided_rules,
            **revising_agents()}
