
import pytest

from app.normalization import normalize_phone, normalize_date


@pytest.mark.parametrize("phone, expected", [
    ("9876543210", "+919876543210"),
    ("+919876543210", "+919876543210"),
    ("919876543210", "+919876543210"),
    ("09876543210", "+919876543210"),
    ("98765-43210", "+919876543210"),
])
def test_normalize_phone_valid(phone, expected):
    assert normalize_phone(phone) == expected


@pytest.mark.parametrize("phone", [
    None,
    "",
    "1234567890",
    "12345",
    "987654321",
])
def test_normalize_phone_invalid(phone):
    with pytest.raises(ValueError):
        normalize_phone(phone)


@pytest.mark.parametrize("date_value, expected", [
    ("2026-10-01", "2026-10-01"),
    ("01/10/2026", "2026-10-01"),
    ("01-10-2026", "2026-10-01"),
    ("01-Oct-2026", "2026-10-01"),
])
def test_normalize_date_valid(date_value, expected):
    assert normalize_date(date_value) == expected


def test_normalize_date_empty():
    assert normalize_date(None) is None
    assert normalize_date("") is None


@pytest.mark.parametrize("date_value", [
    "2026-15-40",
    "invalid-date",
    "32/10/2026",
])
def test_normalize_date_invalid(date_value):
    with pytest.raises(ValueError):
        normalize_date(date_value)
