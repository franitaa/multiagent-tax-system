"""P3 adapter for an existing chat case; no demo facts or routing overrides."""
import re
from pathlib import Path

from silverfile_extraction.checkpointer import case_config
from silverfile_extraction.privacy import SafeInputError
from src.p3.bridge import P3Tools


def make_shared_service(checkpointer, runtime="runtime", reader=None, trace_dir="traces"):
    """Use the chat-owned saver; the caller owns its lifetime.

    How the chat page uses it (JiWon's integration pattern; a sketch, not a complete UI block: `reader`,
    `case_id`, `uploaded_file` and `final_answer` come from the page)::

        from src.ui import chat_session as chat
        from src.p3.shared_service import make_shared_service

        saver = chat.open_saved_sessions()                    # the chat's saved-session storage
        service = make_shared_service(saver, reader=reader)   # reader: a VisionReader for the chosen provider
        graph = service.graph                                 # use THIS graph for every chat operation
        service.submit(case_id, uploaded_file.getvalue(), synthetic_confirmed=True)
        chat.send(graph, case_id, final_answer)               # same graph, same case ID

    What the upload step does:
      * `submit()` saves the image and adds its reference to the existing case. It does not call the model.
      * Extraction runs when the normal graph reaches the Extraction agent, which is when the interview
        ends. Keep the configured reader available during that call, and show the taxpayer a wait message.
      * Use `service.graph`, not `chat.make_graph()`: the adapter registers the P3 tools when compiling,
        not after.
      * Read results with `service.records(case_id)`. Human review is the existing EXTRACTION_REVIEW
        interrupt; `service.resolve(case_id, decision)` resumes it with a validated HumanDecision.
      * Pass `synthetic_confirmed=True` only after the user confirms the image is fictional test data.
      * Reuse one service for the active session and serialize operations on the same case. There is no
        cross-page locking, so disable the upload button while a call runs.

    Timing is a rule, not advice. Upload before the interview's final answer, once the W-2 answer is "yes".
    A taxpayer who says they have a W-2 and has uploaded nothing makes the orchestrator pause the case for a
    volunteer (INCOME_NOT_READ), and `submit()` refuses a document while a volunteer request is pending or
    after the lines are computed, so a late upload is impossible. If uploads must come later, the
    orchestrator needs an explicit upload-wait step.

    Also needed (added by Francesca):
      * The volunteer dashboard must use the same service graph (build the service once and share it),
        otherwise it resumes with a graph that has the default tools, not the P3 ones.
      * The chat page has no provider selector. Decide how the provider is chosen (for example, the key
        present in `.env`), and read the key from the `.env` file as app.py does. Never put a key in state.
      * Approving a reading in the dashboard (service.resolve) is not built yet; today it is done on the
        W-2 page. To check the whole path with a real provider: `python -m scripts.verify_chat_extraction`.

    `trace_dir` is where the runner writes traces and the audit log. Keep the chat's own default
    ("traces"): the volunteer dashboard and the telemetry page read `traces/audit`, so a different
    folder would leave a case's history empty there.
    """
    from src.agents import live_agents
    from src.graph import build_graph

    if checkpointer is None:
        raise ValueError("Pass the chat's saved-session checkpointer.")

    tools = P3Tools(Path(runtime), reader)
    graph = build_graph(
        checkpointer=checkpointer,
        agents=live_agents(),
        tool_registry=tools.registry(),
        trace_dir=trace_dir,
    )
    return SharedExtractionService(graph, tools)


class SharedExtractionService:
    """Attach W-2 references without changing taxpayer answers.

    Calls for one case must be serialized by the caller. This adapter does not
    own the database connection, reopen completed returns, or change routing.
    """

    def __init__(self, graph, tools):
        self.graph = graph
        self.tools = tools

    @property
    def reader(self):
        return self.tools.reader

    @reader.setter
    def reader(self, value):
        self.tools.reader = value

    def _state(self, case_id):
        if not isinstance(case_id, str) or not re.fullmatch(
            r"SF-\d{3}-\d{3}", case_id
        ):
            raise SafeInputError("Use the exact case ID shown by the chat.")

        state = self.graph.get_state(case_config(case_id))

        if not state.values or state.values.get("case_id") != case_id:
            raise SafeInputError(
                "Start this case in the chat before uploading."
            )

        return state

    @staticmethod
    def _check_upload_allowed(state):
        values = state.values

        if values.get("done") or values.get("status") in {
            "complete", "halted_by_human"
        }:
            raise SafeInputError(
                "This case is closed. Do not add a W-2 to a completed draft."
            )

        if (
            getattr(state, "interrupts", ())
            or (values.get("escalation") or {}).get("pending")
        ):
            raise SafeInputError(
                "Resolve the pending volunteer request first."
            )

        if state.next:
            raise SafeInputError(
                "Finish the pending graph operation before adding a document."
            )

        if values.get("computed"):
            raise SafeInputError(
                "This case already has calculated lines. "
                "Ask P1 to arrange a safe revision."
            )

    def submit(self, case_id, data, *, synthetic_confirmed):
        """Queue a W-2 for the next normal graph run; no model call here.

        Upload before the chat's final answer is sent, unless P1 has supplied
        an explicit upload wait. Never set intake_complete from this method.
        """
        state = self._state(case_id)
        self._check_upload_allowed(state)

        if not synthetic_confirmed:
            raise SafeInputError(
                "Confirm fictional test data before uploading."
            )

        if self.reader is None:
            raise SafeInputError(
                "Configure the selected provider in .env before uploading."
            )

        ref = self.tools.upload(data, synthetic_confirmed=True)
        prior = list(state.values.get("documents") or [])

        existing = next(
            (doc for doc in prior if doc["id"] == ref["id"]),
            None,
        )

        if existing is not None:
            if existing.get("image_ref") != ref["image_ref"]:
                raise SafeInputError(
                    "The existing document has a different source reference."
                )
            return {
                "case_id": case_id,
                "document_id": ref["id"],
                "added": False,
            }

        self.graph.update_state(
            case_config(case_id),
            {"documents": [*prior, ref]},
        )

        return {
            "case_id": case_id,
            "document_id": ref["id"],
            "added": True,
        }

    def records(self, case_id):
        """Read the same extraction envelopes used by chat and dashboard."""
        return dict(
            self._state(case_id).values.get("extracted") or {}
        )

    def resolve(self, case_id, decision):
        """Resume only an existing EXTRACTION_REVIEW interrupt."""
        from langgraph.types import Command
        from silverfile_extraction.models import HumanDecision

        decision = HumanDecision.model_validate(decision)
        state = self._state(case_id)
        escalation = state.values.get("escalation") or {}

        if (
            not getattr(state, "interrupts", ())
            or not escalation.get("pending")
            or escalation.get("condition") != "EXTRACTION_REVIEW"
        ):
            raise SafeInputError(
                "There is no pending W-2 review for this case."
            )

        doc_id = escalation.get("document_id")
        envelope = (
            state.values.get("extracted") or {}
        ).get(doc_id)

        if not envelope:
            raise SafeInputError(
                "The pending W-2 evidence could not be found."
            )

        if decision.action == "accept":
            self.tools.registry()["p3_verify_w2"](
                envelope,
                decision.model_dump(mode="json"),
            )

        answer = {
            "decision": (
                "continue" if decision.action == "accept" else "stop"
            ),
            "note": decision.reason,
            "reviewer": decision.reviewer,
        }

        if decision.action == "accept":
            answer["resolution"] = {
                "document_id": doc_id,
                "review": decision.model_dump(mode="json"),
            }

        self.graph.invoke(
            Command(resume=answer),
            case_config(case_id),
        )
        return self.records(case_id)