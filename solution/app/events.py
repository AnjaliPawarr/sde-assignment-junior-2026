
import csv
import json
from datetime import datetime, timezone

from app.config import BASE_DIR, IST
from app.database import get_db
from app.normalization import normalize_phone
from app.security import phone_lookup_hash, encrypt_pii


EVENT_TYPES = {
    "call.initiated",
    "call.connected",
    "call.ended",
    "call.telephony_failed",
    "disposition.set",
    "disposition.override",
}


def load_dispositions():
    """Load valid disposition codes from the provided CSV."""

    path = BASE_DIR / "assignment-a-data" / "schemas" / "dispositions.csv"

    dispositions = {}

    with open(path, newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)

        for row in reader:
            key = (row["workflow_id"], row["code"])

            dispositions[key] = {
                "is_terminal": row["is_terminal"].strip().lower() == "true",
                "is_success": row["is_success"].strip().lower() == "true",
            }

    return dispositions


def parse_event_timestamp(value):
    """
    Parse UTC, offset-aware and naive timestamps.

    Naive timestamps are interpreted as IST.
    All timestamps are stored in UTC.
    """

    if not value:
        raise ValueError("missing_timestamp")

    parsed = datetime.fromisoformat(
        value.strip().replace("Z", "+00:00")
    )

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=IST)

    return parsed.astimezone(timezone.utc).isoformat()


def ingest_event(event, dispositions=None):
    """
    Validate and store one event.

    Returns:
        inserted
        duplicate_event
        missing_event_id
        unknown_event_type
        unknown_disposition
        invalid_event
    """

    if not isinstance(event, dict):
        return "invalid_event"

    event_id = event.get("event_id")

    if not event_id or not str(event_id).strip():
        return "missing_event_id"

    event_id = str(event_id).strip()

    event_type = event.get("event_type")
    workflow_id = event.get("workflow_id")
    call_id = event.get("call_id")
    payload = event.get("payload") or {}

    if event_type not in EVENT_TYPES:
        return "unknown_event_type"

    if not workflow_id or not event.get("occurred_at"):
        return "invalid_event"

    if not isinstance(payload, dict):
        return "invalid_event"

    # Validate disposition codes against the supplied CSV.
    if event_type in {"disposition.set", "disposition.override"}:

        if dispositions is None:
            dispositions = load_dispositions()

        disposition_code = payload.get("disposition_code")

        if (workflow_id, disposition_code) not in dispositions:
            return "unknown_disposition"

    try:
        occurred_at = parse_event_timestamp(event["occurred_at"])
    except (ValueError, TypeError):
        return "invalid_event"

    # Phone is never stored in plaintext.
    phone_hash = None
    phone = event.get("phone")

    if phone:
        try:
            canonical_phone = normalize_phone(phone)
            phone_hash = phone_lookup_hash(canonical_phone)
        except ValueError:
            return "invalid_event"

    disposition = payload.get("disposition_code")

    # Encrypt the event payload before storing it.
    encrypted_payload = encrypt_pii(
        json.dumps(payload, default=str)
    )

    received_at = datetime.now(timezone.utc).isoformat()

    with get_db() as connection:

        # Find an existing lead using workflow + phone HMAC.
        lead = None

        if phone_hash:
            lead = connection.execute(
                """
                SELECT id
                FROM leads
                WHERE workflow_id = ? AND phone_hmac = ?
                """,
                (workflow_id, phone_hash),
            ).fetchone()

        # Overrides can inherit the lead association from their call.
        if lead is None and call_id:
            lead = connection.execute(
                """
                SELECT lead_id
                FROM interactions
                WHERE workflow_id = ? AND call_id = ?
                  AND lead_id IS NOT NULL
                LIMIT 1
                """,
                (workflow_id, call_id),
            ).fetchone()

        lead_id = lead["id"] if lead and "id" in lead.keys() else (
            lead["lead_id"] if lead else None
        )

        try:
            connection.execute(
                """
                INSERT INTO interactions (
                    event_id,
                    workflow_id,
                    lead_id,
                    phone_hmac,
                    event_type,
                    call_id,
                    occurred_at,
                    disposition,
                    payload_encrypted,
                    received_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    workflow_id,
                    lead_id,
                    phone_hash,
                    event_type,
                    call_id,
                    occurred_at,
                    disposition,
                    encrypted_payload,
                    received_at,
                ),
            )
        except Exception as error:
            # A repeated event_id must never create another ledger row.
            if "UNIQUE constraint failed" in str(error):
                return "duplicate_event"
            raise

        # If this event identifies a lead, link earlier orphan events
        # belonging to the same call.
        if lead_id is not None and call_id:
            connection.execute(
                """
                UPDATE interactions
                SET lead_id = ?
                WHERE workflow_id = ?
                  AND call_id = ?
                  AND lead_id IS NULL
                """,
                (lead_id, workflow_id, call_id),
            )

    return "inserted"


def process_jsonl(file_path):
    """Read a JSONL file and count all ingestion outcomes."""

    dispositions = load_dispositions()

    counts = {
        "inserted": 0,
        "duplicate_event": 0,
        "missing_event_id": 0,
        "unknown_event_type": 0,
        "unknown_disposition": 0,
        "invalid_event": 0,
        "malformed_json": 0,
        "blank_lines": 0,
    }

    with open(file_path, encoding="utf-8") as file:

        for line in file:

            if not line.strip():
                counts["blank_lines"] += 1
                continue

            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                counts["malformed_json"] += 1
                continue

            result = ingest_event(event, dispositions)
            counts[result] += 1

    return counts


def link_orphan_events(workflow_id, canonical_phone):
    """
    Link previously stored orphan events after a lead arrives.

    Only the lead association metadata is updated.
    Event identity and event payload remain unchanged.
    """

    phone_hash = phone_lookup_hash(canonical_phone)

    with get_db() as connection:

        lead = connection.execute(
            """
            SELECT id
            FROM leads
            WHERE workflow_id = ? AND phone_hmac = ?
            """,
            (workflow_id, phone_hash),
        ).fetchone()

        if not lead:
            return 0

        cursor = connection.execute(
            """
            UPDATE interactions
            SET lead_id = ?
            WHERE workflow_id = ?
              AND phone_hmac = ?
              AND lead_id IS NULL
            """,
            (lead["id"], workflow_id, phone_hash),
        )

        return cursor.rowcount
