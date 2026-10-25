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


if __name__ == "__main__":
    test_accepts_fake_ssn()
    test_rejects_real_ssn_format()
    test_rejects_invalid_format()
    print("All SSN security tests passed!")
