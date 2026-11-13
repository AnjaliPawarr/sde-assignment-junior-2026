
import os
import hmac
import hashlib

from cryptography.fernet import Fernet, InvalidToken


def _get_fernet():
    """Create Fernet encryption instance using environment key."""

    key = os.getenv("PII_ENCRYPTION_KEY")

    if not key:
        raise RuntimeError(
            "PII_ENCRYPTION_KEY environment variable is missing"
        )

    try:
        return Fernet(key.encode("utf-8"))
    except (ValueError, TypeError):
        raise RuntimeError("Invalid PII_ENCRYPTION_KEY")


def _get_hmac_key():
    """Read the secret key used for deterministic phone lookup."""

    key = os.getenv("PII_HMAC_KEY")

    if not key:
        raise RuntimeError(
            "PII_HMAC_KEY environment variable is missing"
        )

    return key.encode("utf-8")


def encrypt_pii(value):
    """Encrypt personal information before storing it."""

    if value is None:
        return None

    plaintext = str(value).encode("utf-8")
    encrypted = _get_fernet().encrypt(plaintext)

    return encrypted.decode("utf-8")


def decrypt_pii(encrypted_value):
    """Decrypt previously encrypted personal information."""

    if encrypted_value is None:
        return None

    try:
        decrypted = _get_fernet().decrypt(
            encrypted_value.encode("utf-8")
        )
        return decrypted.decode("utf-8")
    except InvalidToken:
        raise ValueError("Unable to decrypt PII")


def phone_lookup_hash(canonical_phone):
    """
    Generate deterministic HMAC-SHA256 hash.

    Same phone + same secret key = same hash.
    This allows duplicate matching without storing plaintext phone.
    """

    if not canonical_phone:
        raise ValueError("Phone number cannot be empty")

    return hmac.new(
        _get_hmac_key(),
        canonical_phone.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
