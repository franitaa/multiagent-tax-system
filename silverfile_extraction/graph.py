"""Checkpoint validated extraction and pause for human review. P1 owns the full graph."""
from typing import Annotated, TypedDict

from langgraph.graph import START, END, StateGraph
from langgraph.types import interrupt

from .memory import merge_documents, merge_versioned
from .models import Document, ExtractionRecord, HumanDecision
from .review import apply_human_decision


class ExtractionState(TypedDict, total=False):
    documents: Annotated[dict, merge_documents]
    records: Annotated[dict, merge_versioned]
    current_document_id: str


def human_check(state: ExtractionState) -> dict:
    current = state["current_document_id"]
    record = ExtractionRecord.model_validate(state["records"][current])
    if record.status != "needs_review":
        return {}
    response = interrupt({"type": "extraction_review", "document_id": current,
                          "issues": [x.model_dump(mode="json") for x in record.issues]})
    updated = apply_human_decision(Document.model_validate(state["documents"][current]), record,
                                  HumanDecision.model_validate(response))
    return {"records": {current: updated.model_dump(mode="json")}}


def build_graph(checkpointer):
    builder = StateGraph(ExtractionState)
    builder.add_node("human_extraction_check", human_check)
    builder.add_edge(START, "human_extraction_check")
    builder.add_edge("human_extraction_check", END)
    return builder.compile(checkpointer=checkpointer)
