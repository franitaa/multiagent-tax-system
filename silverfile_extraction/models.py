"""Versioned, JSON-safe handoff contracts. Currency is never a float."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Box = Literal["1", "2", "3", "4", "5", "6", "7", "8", "10", "11"]
BOX_LABELS = {
    "1": "Wages, tips, other compensation",
    "2": "Federal income tax withheld",
    "3": "Social security wages",
    "4": "Social security tax withheld",
    "5": "Medicare wages and tips",
    "6": "Medicare tax withheld",
    "7": "Social security tips",
    "8": "Allocated tips",
    "10": "Dependent care benefits",
    "11": "Nonqualified plans",
}
REQUIRED_BOXES = ("1", "2")
MONEY = re.compile(r"^\$?(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}$")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def money_string(raw: str) -> str:
    """Normalize a printed amount; do not infer decimals, blanks, or signs."""
    raw = raw.strip()
    if not MONEY.fullmatch(raw):
        raise ValueError("Use a nonnegative amount with two decimal places, e.g. 30000.00.")
    value = Decimal(raw.replace("$", "").replace(",", ""))
    if value > Decimal("999999999.99"):
        raise ValueError("Amount exceeds the supported transcription range.")
    return format(value, ".2f")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OCRToken(StrictModel):
    id: str
    text: str
    confidence: float
    bbox: tuple[int, int, int, int]
    line_id: str


class Document(StrictModel):
    document_id: str
    sha256: str
    image_width: int
    image_height: int
    image_file: str
    ocr_engine: str
    tokens: list[OCRToken]
    captured_at: str


class Source(StrictModel):
    document_id: str
    document_sha256: str
    page: int = 1
    box: Box
    label: str
    token_ids: list[str]
    bbox: tuple[int, int, int, int] | None
    observed_text: str
    method: Literal["ocr", "vision_transcription", "human_transcription"]
    recorded_at: str
    actor: str
    note: str | None = None


class Amount(StrictModel):
    value: str
    currency: Literal["USD"] = "USD"
    source: Source
    ocr_confidence: float | None = Field(default=None, ge=0, le=100)
    vision_confidence: Literal["high", "medium", "low"] | None = None


class Issue(StrictModel):
    code: str
    message: str
    box: str | None = None


class Usage(StrictModel):
    # Local token counts and provider billing counts must never be conflated.
    prompt_text_tokens: int | None
    api_input_tokens: int | None = None
    api_output_tokens: int | None = None
    model: str | None = None
    request_id: str | None = None


class ExtractionRecord(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    document_id: str
    document_type: Literal["W-2", "unknown"]
    tax_year: int | None
    fields: dict[str, Amount]
    issues: list[Issue]
    status: Literal["ready_for_rules", "needs_review", "rejected"]
    backend: str
    usage: Usage
    unstructured_sections: list[str] = Field(
        default_factory=lambda: ["12", "13", "14", "15", "16", "17", "18", "19", "20"]
    )
    revision: int = 1
    # Preserve the previous extraction when a reviewer supplies corrections.
    review_history: list[dict] = Field(default_factory=list)
    conflicts: list[dict] = Field(default_factory=list)
    observations: dict = Field(default_factory=dict)


class HumanDecision(StrictModel):
    action: Literal["accept", "reject"]
    reviewer: str = Field(min_length=1, max_length=80)
    reason: str = Field(min_length=1, max_length=300)
    corrections: dict[str, str] = Field(default_factory=dict)
    confirmed_w2: bool = False
    tax_year: int | None = Field(default=None, ge=1900, le=2100)


class FieldSelection(StrictModel):
    box: Box
    token_id: str


class ModelSelection(StrictModel):
    """The model chooses existing tokens; it cannot invent currency values."""

    document_type: Literal["W-2", "unknown"]
    tax_year_token_id: str | None
    fields: list[FieldSelection]

