"""Synthetic-input boundary. OCR screening is best effort, not a DLP guarantee."""

import re

SSN = re.compile(r"(?<!\d)(\d{3})[- ]?(\d{2})[- ]?(\d{4})(?!\d)")
EIN = re.compile(r"(?<!\d)\d{2}-\d{7}(?!\d)")


class SafeInputError(ValueError):
    """A user-displayable error which never echoes rejected input."""


def redact_identifiers(text: str) -> str:
    return EIN.sub("[EIN REDACTED]", SSN.sub("[SSN REDACTED]", text))


def reject_non_test_ssns(text: str) -> None:
    for match in SSN.finditer(text):
        if not 900 <= int(match.group(1)) <= 999:
            raise SafeInputError(
                "Rejected: detected an SSN outside the assignment's 900-series test range. "
                "Use synthetic documents only. No document state was saved."
            )

