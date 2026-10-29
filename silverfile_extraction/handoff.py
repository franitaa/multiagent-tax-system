"""EXT-3 and P5 adapter. Proposed JSON shape; P4/P5 own the final shared types."""
from pydantic import Field

from .models import ExtractionRecord, Issue, StrictModel, money_string
from .privacy import SafeInputError


class UserAmountClaim(StrictModel):
    document_id: str
    box: str
    value: str
    entered_by: str = Field(min_length=1)
    recorded_at: str = Field(min_length=1)
    # Only like-for-like claims are compared. Never compare a household total to one W-2.
    scope: str = "single_document"


def flag_document_conflicts(record: ExtractionRecord, claims: list[UserAmountClaim]) -> ExtractionRecord:
    issues = list(record.issues)
    conflicts = list(record.conflicts)
    for claim in claims:
        if claim.scope != "single_document":
            raise SafeInputError("Compare only claims explicitly attached to one document and box.")
        if claim.document_id != record.document_id:
            continue
        field = record.fields.get(claim.box)
        if field is None:
            continue
        value = money_string(claim.value)
        if value != field.value:
            conflict = {"document_id": record.document_id, "box": claim.box,
                        "document_value": field.value, "user_claim": claim.model_dump(mode="json")}
            if conflict not in conflicts:
                conflicts.append(conflict)
                issues.append(Issue(code="DOCUMENT_USER_CONFLICT", box=claim.box,
                                    message="User statement and document differ. A human must resolve this."))
    return record.model_copy(update={"issues": issues, "conflicts": conflicts,
                                    "status": "needs_review" if issues else record.status})


def to_p5_provenance(record: ExtractionRecord) -> dict:
    """Transcription only; no formula, invented computation tool, or return-line mapping."""
    if record.status != "ready_for_rules" or record.issues:
        raise SafeInputError("Resolve extraction issues before exporting monetary inputs.")
    return {box: {"value": amount.value, "formula": None, "inputs": {},
                  "source": amount.source.model_dump(mode="json"), "tool": None}
            for box, amount in record.fields.items()}

