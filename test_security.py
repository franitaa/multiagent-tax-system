from security import is_fake_ssn, redact_pii, ssn_redaction_message

def test_ssn_redaction_message():
    message = ssn_redaction_message()

    assert "removed a number that looked like an SSN" in message
    assert "test numbers" in message
    assert "starting with 9" in message


def test_accepts_fake_ssn():
    assert is_fake_ssn("901-23-4567") is True
    assert is_fake_ssn("999-12-3456") is True
    assert is_fake_ssn("900123456") is True


def test_rejects_real_ssn_format():
    assert is_fake_ssn("123-45-6789") is False
    assert is_fake_ssn("899-12-3456") is False


def test_rejects_invalid_format():
    assert is_fake_ssn("90-123-4567") is False
    assert is_fake_ssn("90112345") is False
    assert is_fake_ssn("") is False


def test_redact_pii():
    text = (
        "Test SSN 900-12-3456, real-looking SSN 123-45-6789, "
        "EIN 12-3456789, email test@example.com, "
        "phone (212) 555-1234"
    )

    result = redact_pii(text)

    # Approved test SSNs should be preserved.
    assert "900-12-3456" in result

    # Real-looking SSNs should be redacted.
    assert "123-45-6789" not in result
    assert "[REDACTED SSN]" in result

    # Other sensitive identifiers should be redacted.
    assert "12-3456789" not in result
    assert "[REDACTED EIN]" in result
    assert "test@example.com" not in result
    assert "[REDACTED EMAIL]" in result
    assert "(212) 555-1234" not in result
    assert "[REDACTED PHONE]" in result


def test_redact_pii_preserves_normal_text():
    text = "Calculation complete: taxable income is 25000."
    assert redact_pii(text) == text


def test_redact_pii_rejects_non_string():
    try:
        redact_pii(None)
    except TypeError:
        return

    raise AssertionError("Expected TypeError for non-string input")


if __name__ == "__main__":
    test_accepts_fake_ssn()
    test_rejects_real_ssn_format()
    test_rejects_invalid_format()
    test_redact_pii()
    test_redact_pii_preserves_normal_text()
    test_redact_pii_rejects_non_string()
    print("All SSN security and PII redaction tests passed!")
