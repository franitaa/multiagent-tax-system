import re


def is_fake_ssn(ssn: str) -> bool:
    """Return True only for a 9-digit test SSN starting with 900–999.

    Accepts either 9 consecutive digits or the format XXX-XX-XXXX.
    Rejects real-looking SSNs and incorrectly formatted values.
    """
    if not isinstance(ssn, str):
        return False

    # Accept only the two supported formats.
    if re.fullmatch(r"\d{3}-\d{2}-\d{4}", ssn):
        digits = ssn.replace("-", "")
    elif re.fullmatch(r"\d{9}", ssn):
        digits = ssn
    else:
        return False

    prefix = int(digits[:3])
    return 900 <= prefix <= 999


def redact_pii(text: str) -> str:
    """Redact sensitive identifiers while preserving approved test SSNs.

    This is a defensive filter, not a guarantee that all PII is removed.
    """
    if not isinstance(text, str):
        raise TypeError("text must be a string")

    def redact_ssn(match):
        candidate = match.group(0)

        # Reuse the shared validator rather than creating another SSN rule.
        if is_fake_ssn(candidate):
            return candidate

        return "[REDACTED SSN]"

    # Redact SSN-shaped values unless the shared validator approves them.
    text = re.sub(
        r"(?<!\d)(?:\d{3}-\d{2}-\d{4}|\d{9})(?!\d)",
        redact_ssn,
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

    # Redact common US-style phone numbers.
    text = re.sub(
        r"(?<!\d)(?:\+1[-.\s]?)?(?:\(\d{3}\)|\d{3})[-.\s]\d{3}[-.\s]\d{4}(?!\d)",
        "[REDACTED PHONE]",
        text,
    )

    return text


def ssn_redaction_message() -> str:
    """Explain SSN redaction without revealing the original number."""
    return (
        "I removed a number that looked like an SSN. "
        "For this practice system, please only use test numbers "
        "starting with 9."
    )
