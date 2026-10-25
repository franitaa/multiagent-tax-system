import re


def is_fake_ssn(ssn: str) -> bool:
    """Return True only for a 9-digit test SSN starting with 900–999.

    Accepts either 9 consecutive digits or the format XXX-XX-XXXX.
    Rejects real SSNs and incorrectly formatted values.
    """
    if not isinstance(ssn, str):
        return False

    # Remove hyphens only when they are in the expected positions.
    if re.fullmatch(r"\d{3}-\d{2}-\d{4}", ssn):
        digits = ssn.replace("-", "")
    elif re.fullmatch(r"\d{9}", ssn):
        digits = ssn
    else:
        return False

    prefix = int(digits[:3])
    return 900 <= prefix <= 999



def redact_pii(text: str) -> str:
    """Redact common sensitive identifiers before text is written to logs.

    Masks SSNs, EINs, email addresses, and US-style phone numbers.
    This is a defensive filter, not a guarantee that all PII is removed.
    """
    import re

    if not isinstance(text, str):
        raise TypeError("text must be a string")

    # Redact SSNs such as 900-12-3456 or 900123456.
    text = re.sub(
        r"(?<!\d)(?:\d{3}-\d{2}-\d{4}|\d{9})(?!\d)",
        "[REDACTED SSN]",
        text,
    )

    # Redact EINs such as 12-3456789.
    text = re.sub(
        r"(?<!\d)\d{2}-\d{7}(?!\d)",
        "[REDACTED EIN]",
        text,
    )

    # Redact email addresses.
    text = re.sub(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        "[REDACTED EMAIL]",
        text,
    )

    # Redact common US phone-number formats.
    text = re.sub(
        r"(?<!\d)(?:\+1[-.\s]?)?(?:\(\d{3}\)|\d{3})[-.\s]\d{3}[-.\s]\d{4}(?!\d)",
        "[REDACTED PHONE]",
        text,
    )

    return text
