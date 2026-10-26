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
