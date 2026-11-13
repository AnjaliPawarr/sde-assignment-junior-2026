
import re
from datetime import datetime, date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def normalize_phone(value):
    """
    Normalize an Indian phone number to +91XXXXXXXXXX.

    Accepted examples:
    9876543210
    +919876543210
    919876543210
    09876543210
    """

    if value is None:
        raise ValueError("invalid_phone")

    digits = re.sub(r"\D", "", str(value))

    # Remove country code 91
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]

    # Remove leading zero
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]

    # Indian mobile numbers must have 10 digits
    if len(digits) != 10 or digits[0] not in "6789":
        raise ValueError("invalid_phone")

    return "+91" + digits


def normalize_date(value):
    """
    Convert supported date formats into YYYY-MM-DD.

    Supported:
    YYYY-MM-DD
    DD/MM/YYYY
    DD-MM-YYYY
    DD-Mon-YYYY
    """

    if value is None or not str(value).strip():
        return None

    value = str(value).strip()

    formats = [
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d-%b-%Y",
    ]

    for fmt in formats:
        try:
            parsed = datetime.strptime(value, fmt)
            return parsed.date().isoformat()
        except ValueError:
            continue

    raise ValueError("invalid_date")


def normalize_decimal(value):
    """
    Normalize currency values into a Decimal with 2 decimal places.

    Examples:
    ₹27,554 -> 27554.00
    Rs. 6,850 -> 6850.00
    INR 1200.5 -> 1200.50
    """

    if value is None or not str(value).strip():
        return None

    amount = str(value).strip()

    # Remove currency prefixes
    amount = re.sub(
        r"(?i)^(?:INR|RS\.?|₹|â‚¹)\s*",
        "",
        amount
    )

    # Remove thousands separators
    amount = amount.replace(",", "").strip()

    try:
        result = Decimal(amount)
    except InvalidOperation:
        raise ValueError("invalid_decimal")

    if not result.is_finite() or result < 0:
        raise ValueError("invalid_decimal")

    return result.quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP
    )
