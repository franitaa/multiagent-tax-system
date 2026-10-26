from security import is_fake_ssn


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


from security import redact_pii


def test_redact_pii():
    text = (
        "SSN 900-12-3456, EIN 12-3456789, "
        "email test@example.com, phone (212) 555-1234"
    )

    result = redact_pii(text)

    assert "900-12-3456" not in result
    assert "12-3456789" not in result
    assert "test@example.com" not in result
    assert "(212) 555-1234" not in result

    assert "[REDACTED SSN]" in result
    assert "[REDACTED EIN]" in result
    assert "[REDACTED EMAIL]" in result
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