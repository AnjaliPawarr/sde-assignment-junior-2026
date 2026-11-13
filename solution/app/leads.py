
import json
from datetime import datetime, timezone
from decimal import Decimal

from app.database import get_db
from app.normalization import normalize_phone
from app.security import (
    encrypt_pii,
    decrypt_pii,
    phone_lookup_hash,
)


PII_FIELDS = {"customer_name", "phone"}


def json_dumps(data):
    """Serialize dictionaries safely, including Decimal values."""
    return json.dumps(data, default=str)


def upsert_lead(workflow_id, lead_data, batch_id):
    """
    Insert a new lead or update an existing lead.

    Identity:
        workflow_id + canonical phone HMAC

    Update rule:
        Only non-null values overwrite existing values.
        Original batch_id is preserved.
    """

    phone = normalize_phone(lead_data.get("phone"))
    phone_hash = phone_lookup_hash(phone)

    pii_data = {
        key: value
        for key, value in lead_data.items()
        if key in PII_FIELDS and key != "phone" and value is not None
    }

    non_pii_data = {
        key: value
        for key, value in lead_data.items()
        if key not in PII_FIELDS and value is not None
    }

    now = datetime.now(timezone.utc).isoformat()

    with get_db() as connection:

        existing = connection.execute(
            """
            SELECT *
            FROM leads
            WHERE workflow_id = ? AND phone_hmac = ?
            """,
            (workflow_id, phone_hash),
        ).fetchone()

        if existing is None:

            connection.execute(
                """
                INSERT INTO leads (
                    workflow_id,
                    phone_hmac,
                    phone_encrypted,
                    pii_data_encrypted,
                    non_pii_data,
                    batch_id,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    workflow_id,
                    phone_hash,
                    encrypt_pii(phone),
                    encrypt_pii(json_dumps(pii_data)),
                    json_dumps(non_pii_data),
                    batch_id,
                    now,
                    now,
                ),
            )

            return "inserted"

        # Decrypt existing PII before merging
        old_pii = json.loads(
            decrypt_pii(existing["pii_data_encrypted"])
        )

        old_non_pii = json.loads(existing["non_pii_data"])

        # Last non-null value wins
        old_pii.update(pii_data)
        old_non_pii.update(non_pii_data)

        connection.execute(
            """
            UPDATE leads
            SET pii_data_encrypted = ?,
                non_pii_data = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                encrypt_pii(json_dumps(old_pii)),
                json_dumps(old_non_pii),
                now,
                existing["id"],
            ),
        )

        return "updated"
