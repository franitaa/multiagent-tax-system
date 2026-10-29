"""Manual extraction correction, not the team's Review / Audit agent."""

from .models import (
    BOX_LABELS, REQUIRED_BOXES, Amount, Document, ExtractionRecord,
    HumanDecision, Source, money_string, utc_now,
)
from .privacy import SafeInputError, SSN


def apply_human_decision(document: Document, record: ExtractionRecord,
                         decision: HumanDecision) -> ExtractionRecord:
    if not decision.reviewer.strip() or not decision.reason.strip():
        raise SafeInputError("A reviewer identifier and a reason are required.")
    if SSN.search(decision.reviewer + " " + decision.reason):
        raise SafeInputError("Do not include SSNs in reviewer names or notes.")
    fields = dict(record.fields)
    if any(box not in BOX_LABELS for box in decision.corrections):
        raise SafeInputError("A correction refers to an unsupported W-2 box.")
    if decision.action == "accept":
        unreadable = {issue.box for issue in record.issues
                      if issue.box and issue.code in {"MISSING_OR_UNREADABLE_BOX", "AMBIGUOUS_BOX", "UNREADABLE_AMOUNT"}}
        if any(box not in decision.corrections for box in unreadable):
            raise SafeInputError("Supply a verified amount for every unreadable or ambiguous box, or reject this image.")
        if any(c["box"] not in decision.corrections for c in record.conflicts):
            raise SafeInputError("Explicitly confirm an amount for every conflicting box and record why.")
        if not decision.confirmed_w2:
            raise SafeInputError("Confirm visually that the document is a W-2 before accepting it.")
        for box, raw in decision.corrections.items():
            try:
                value = money_string(raw)
            except ValueError as exc:
                raise SafeInputError(str(exc)) from exc
            fields[box] = Amount(value=value, source=Source(
                document_id=document.document_id, document_sha256=document.sha256,
                box=box, label=BOX_LABELS[box], token_ids=[], bbox=None,
                observed_text=raw, method="human_transcription", recorded_at=utc_now(),
                actor=decision.reviewer, note=decision.reason,
            ))
        if any(box not in fields for box in REQUIRED_BOXES):
            raise SafeInputError("Supply readable values for boxes 1 and 2; do not assume blank is zero.")
        if not (decision.tax_year or record.tax_year):
            raise SafeInputError("The reviewer must supply the printed tax year.")
    event = {
        "at": utc_now(), "reviewer": decision.reviewer, "reason": decision.reason,
        "action": decision.action,
        "previous_fields": {k: v.model_dump(mode="json") for k, v in record.fields.items()},
        "previous_issues": [i.model_dump(mode="json") for i in record.issues],
        "previous_tax_year": record.tax_year,
        "previous_conflicts": record.conflicts,
    }
    return record.model_copy(update={
        "fields": fields,
        "status": "ready_for_rules" if decision.action == "accept" else "rejected",
        "issues": [] if decision.action == "accept" else record.issues,
        "conflicts": [] if decision.action == "accept" else record.conflicts,
        "document_type": "W-2" if decision.action == "accept" else record.document_type,
        "tax_year": decision.tax_year or record.tax_year,
        "revision": record.revision + 1,
        "review_history": [*record.review_history, event],
    })

