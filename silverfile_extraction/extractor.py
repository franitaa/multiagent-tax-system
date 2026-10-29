"""Direct vision extraction with explicit, reviewable image provenance."""
from .image_input import prepare_image
from .models import BOX_LABELS, REQUIRED_BOXES, Amount, Document, ExtractionRecord, Issue, Source, Usage, money_string, utc_now
from .privacy import SSN, SafeInputError
from .vision import VisionResult, build_context


def assemble_record(document: Document, result: VisionResult, usage: Usage) -> ExtractionRecord:
    """Reject detected non-test identifiers; never treat model text as OCR-verified."""
    if result.ssn_status in {"non_test", "unreadable"}:
        raise SafeInputError("The image contains a non-test or unreadable SSN. Use a clear synthetic W-2 only.")
    if any(len(prefix) != 3 or not prefix.isdigit() or not 900 <= int(prefix) <= 999
           for prefix in result.ssn_prefixes):
        raise SafeInputError("A detected SSN prefix is outside the 900-series test range. Nothing was saved.")
    if (result.ssn_status == "test_only" and not result.ssn_prefixes) or (
            result.ssn_status == "absent" and result.ssn_prefixes):
        raise SafeInputError("The model returned inconsistent identifier screening. Try a clearer image.")
    fields = {}
    seen = set()
    issues = [Issue(code="VISION_REVIEW_REQUIRED",
                    message="Compare every extracted amount with the source image before accepting.")]
    for field in result.fields:
        if SSN.search(field.observed_text):
            raise SafeInputError("Identifier-like text appeared in an amount. Nothing was saved.")
        if field.box in seen:
            fields.pop(field.box, None)
            issues.append(Issue(code="AMBIGUOUS_BOX", box=field.box,
                                message="Multiple values were returned for one box."))
            continue
        seen.add(field.box)
        try:
            amount = money_string(field.observed_text)
        except ValueError:
            issues.append(Issue(code="UNREADABLE_AMOUNT", box=field.box,
                                message="No valid printed amount was read for this box."))
            continue
        fields[field.box] = Amount(value=amount, vision_confidence=field.confidence, source=Source(
            document_id=document.document_id, document_sha256=document.sha256,
            box=field.box, label=BOX_LABELS[field.box], token_ids=[], bbox=None,
            observed_text=field.observed_text, method="vision_transcription", recorded_at=utc_now(),
            actor=usage.model or "openai-vision",
            note="Model-reported transcription from the source image; no local OCR or exact bounding box. Human verification required.",
        ))
        if field.confidence != "high":
            issues.append(Issue(code="LOW_VISION_CONFIDENCE", box=field.box,
                                message="The model reported uncertainty; inspect this printed box."))
    for box in set(REQUIRED_BOXES) | set(result.unreadable_boxes):
        if box not in fields or box in result.unreadable_boxes:
            issues.append(Issue(code="MISSING_OR_UNREADABLE_BOX", box=box,
                                message="Read this box from a clearer source; blank is not zero."))
    year = result.tax_year
    if year is None or not 1900 <= year <= 2100:
        year = None
        issues.append(Issue(code="UNREADABLE_YEAR", message="Confirm the printed tax year."))
    if result.document_type != "W-2":
        issues.append(Issue(code="UNKNOWN_DOCUMENT", message="The image was not identified as a W-2."))
    if result.other_boxes != "blank":
        issues.append(Issue(code="UNSTRUCTURED_W2_ENTRIES",
                            message="Boxes 12-20 may contain entries. Rules must inspect the source image."))
    return ExtractionRecord(document_id=document.document_id, document_type=result.document_type,
                            tax_year=year, fields=fields, issues=issues, status="needs_review",
                            backend="openai-direct", usage=usage,
                            observations={"boxes_12_to_20": result.other_boxes,
                                          "identifier_screening": "model_assisted_not_guaranteed"})


def extract_w2(data: bytes, reader, *, synthetic_confirmed: bool, records: dict | None = None,
               context_strategy: bool = True):
    """P3 agent entry point for P1: returns (Document, ExtractionRecord, normalized PNG).

    No tax calculation or taxpayer dialogue. No filesystem writes. The key lives only
    in the injected reader. The caller persists the returned evidence after validation.
    """
    document, png = prepare_image(data, synthetic_confirmed=synthetic_confirmed)
    result, usage = reader.read(png, build_context(records or {}, context_strategy=context_strategy))
    record = assemble_record(document, result, usage)
    record.backend = getattr(reader, "provider", "openai") + "-direct"
    return document, record, png
