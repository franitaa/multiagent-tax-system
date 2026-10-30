"""Local workbench facade: direct vision, validated persistence, and human resume."""
import hashlib
import json
from pathlib import Path

from .checkpointer import case_config, sqlite_checkpointer
from .extractor import extract_w2
from .handoff import UserAmountClaim, flag_document_conflicts
from .image_input import save_source
from .models import Document, ExtractionRecord, HumanDecision, utc_now, money_string
from .privacy import SSN, SafeInputError
from .review import apply_human_decision


class ExtractionService:
    def __init__(self, runtime="runtime", *, reader=None):
        self.runtime = Path(runtime)
        self.reader = reader  # Never inserted into a checkpoint, config, trace, or export.

    def __enter__(self):
        from .graph import build_graph
        self.runtime.mkdir(parents=True, exist_ok=True)
        self._manager = sqlite_checkpointer(self.runtime / "direct_vision_checkpoints.sqlite")
        self.graph = build_graph(self._manager.__enter__())
        return self

    def __exit__(self, *args):
        return self._manager.__exit__(*args)

    def snapshot(self, case_id):
        state = self.graph.get_state(case_config(case_id))
        values = state.values or {}
        records = values.get("records", {})
        return {"session_id": case_id, "pending": bool(state.next),
                "current_document_id": values.get("current_document_id"),
                "documents": values.get("documents", {}), "records": records,
                "summary": {"documents": len(records),
                            **{s: sum(r["status"] == s for r in records.values())
                               for s in ["ready_for_rules", "needs_review", "rejected"]}}}

    def _trace(self, case_id, event, doc_id):
        with (self.runtime / "events.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"at": utc_now(), "case_id": case_id,
                                     "event": event, "document_id": doc_id}) + "\n")

    def submit(self, case_id, data, *, synthetic_confirmed, context_strategy=True, user_claims=None):
        config = case_config(case_id)
        if not synthetic_confirmed:
            raise SafeInputError("Confirm fictional test data and consent to send the image to OpenAI.")
        state = self.snapshot(case_id)
        doc_id = "doc_" + hashlib.sha256(data).hexdigest()
        if doc_id in state["records"]:
            if user_claims:
                raise SafeInputError("Route new claims about existing documents through the parent review flow.")
            return state  # Idempotent duplicate upload: no second API call.
        if state["pending"]:
            raise SafeInputError("Finish or reject the pending document review before uploading another.")
        if self.reader is None:
            raise SafeInputError("Configure the selected provider's API key in the project-root .env file using OPENAI_API_KEY or ANTHROPIC_API_KEY, then save the file and reload the page.")
        claims = [UserAmountClaim.model_validate(x) for x in (user_claims or [])]
        for claim in claims:
            money_string(claim.value)
            if claim.scope != "single_document" or SSN.search(claim.entered_by + claim.recorded_at):
                raise SafeInputError("Use document-specific claims with no SSNs in the metadata.")
        # No persistent input state/image is written until the response passes validation.
        document, record, png = extract_w2(data, self.reader, synthetic_confirmed=True,
                                          records=state["records"], context_strategy=context_strategy)
        record = flag_document_conflicts(record, claims)
        save_source(document, png, self.runtime / "documents")
        self.graph.invoke({"documents": {doc_id: document.model_dump(mode="json")},
                           "records": {doc_id: record.model_dump(mode="json")},
                           "current_document_id": doc_id}, config)
        self._trace(case_id, "vision_extracted_awaiting_review", doc_id)
        return self.snapshot(case_id)

    def resolve(self, case_id, decision: HumanDecision):
        from langgraph.types import Command
        snapshot = self.snapshot(case_id)
        current = snapshot["current_document_id"]
        record = snapshot["records"].get(current)
        if not snapshot["pending"] or not record or record["status"] != "needs_review":
            raise SafeInputError("There is no pending extraction review for this case.")
        apply_human_decision(Document.model_validate(snapshot["documents"][current]),
                             ExtractionRecord.model_validate(record), decision)
        self.graph.invoke(Command(resume=decision.model_dump(mode="json")), case_config(case_id))
        self._trace(case_id, "human_review_completed", current)
        return self.snapshot(case_id)
