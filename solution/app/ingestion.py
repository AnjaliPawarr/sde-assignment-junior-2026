
import csv
import hashlib
import json
import re
import uuid
from pathlib import Path
from datetime import datetime, timezone

from app.config import BASE_DIR
from app.database import get_db, initialize_database
from app.events import process_jsonl, link_orphan_events
from app.leads import upsert_lead
from app.normalization import (
    normalize_phone,
    normalize_date,
    normalize_decimal,
)
from app.security import encrypt_pii


SCHEMA_DIR = BASE_DIR / "assignment-a-data" / "schemas"


# --------------------------------------------------
# Schema loading
# --------------------------------------------------

def load_schema(workflow_id):
    schema_path = SCHEMA_DIR / f"{workflow_id}.json"

    if not schema_path.exists():
        raise FileNotFoundError(
            f"Schema not found for workflow: {workflow_id}"
        )

    with schema_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def normalize_header(value):
    value = str(value or "").strip().lower()
    return re.sub(r"[^a-z0-9]", "", value)


def build_header_mapping(headers, fields):
    normalized_headers = {
        normalize_header(header): header
        for header in headers
    }

    mapping = {}

    for field in fields:
        field_name = field["name"]

        possible_names = [
            field_name,
            *field.get("aliases", []),
        ]

        for name in possible_names:
            normalized = normalize_header(name)

            if normalized in normalized_headers:
                mapping[field_name] = normalized_headers[normalized]
                break

    return mapping


# --------------------------------------------------
# Field validation and normalization
# --------------------------------------------------

def parse_field(value, field):
    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    field_type = field.get("type", "string")

    if field_type == "string":
        return value

    if field_type == "phone":
        return normalize_phone(value)

    if field_type == "date":
        return normalize_date(value)

    if field_type == "decimal":
        result = normalize_decimal(value)
        return str(result) if result is not None else None

    if field_type == "enum":
        value = value.lower()
        allowed_values = [
            str(item).lower()
            for item in field.get("values", [])
        ]

        if value not in allowed_values:
            raise ValueError("invalid_enum")

        return value

    return value


def parse_lead_row(row, fields, header_mapping):
    lead_data = {}
    warnings = 0

    for field in fields:
        field_name = field["name"]
        required = field.get("required", False)

        source_column = header_mapping.get(field_name)
        raw_value = row.get(source_column) if source_column else None

        if raw_value is None or str(raw_value).strip() == "":
            lead_data[field_name] = None

            if required:
                return (
                    None,
                    f"missing_required:{field_name}",
                    warnings,
                )

            continue

        try:
            normalized_value = parse_field(raw_value, field)

            if normalized_value is None:
                raise ValueError("invalid_value")

            lead_data[field_name] = normalized_value

        except Exception:
            if required:
                if field.get("type") == "phone":
                    reason = "invalid_phone"
                else:
                    reason = f"invalid_{field_name}"

                return None, reason, warnings

            lead_data[field_name] = None
            warnings += 1

    return lead_data, None, warnings


# --------------------------------------------------
# File tracking and idempotency
# --------------------------------------------------

def file_hash(file_path):
    digest = hashlib.sha256()

    with open(file_path, "rb") as file:
        for chunk in iter(lambda: file.read(65536), b""):
            digest.update(chunk)

    return digest.hexdigest()


def make_batch_id(drop_name, source_file, content_hash):
    unique_value = (
        f"{drop_name}:{source_file}:{content_hash}"
    )

    return str(
        uuid.uuid5(uuid.NAMESPACE_URL, unique_value)
    )


def file_already_ingested(drop_name, source_file, content_hash):
    with get_db() as db:
        result = db.execute(
            """
            SELECT id
            FROM ingested_files
            WHERE drop_name = ?
              AND source_file = ?
              AND content_hash = ?
            """,
            (drop_name, source_file, content_hash),
        ).fetchone()

    return result is not None


def record_file_ingestion(
        drop_name,
        source_file,
        content_hash,
        batch_id,
        counts,
):
    now = datetime.now(timezone.utc).isoformat()

    counts_json = json.dumps(counts, sort_keys=True)

    with get_db() as db:
        db.execute(
            """
            INSERT OR IGNORE INTO ingestion_batches
            (id, drop_name, source_file, content_hash,
             ingested_at, counts_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                batch_id,
                drop_name,
                source_file,
                content_hash,
                now,
                counts_json,
            ),
        )

        db.execute(
            """
            INSERT OR IGNORE INTO ingested_files
            (drop_name, source_file, content_hash,
             batch_id, ingested_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                drop_name,
                source_file,
                content_hash,
                batch_id,
                now,
            ),
        )


# --------------------------------------------------
# Rejection handling
# --------------------------------------------------

def save_rejection(
        workflow_id,
        source_file,
        row_number,
        reason,
        row_data,
):
    encrypted_row = encrypt_pii(
        json.dumps(row_data, ensure_ascii=False)
    )

    with get_db() as db:
        db.execute(
            """
            INSERT INTO rejections
            (workflow_id, source_file, row_number,
             reason, row_data_encrypted, rejected_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                workflow_id,
                source_file,
                row_number,
                reason,
                encrypted_row,
                datetime.now(timezone.utc).isoformat(),
            ),
        )


# --------------------------------------------------
# CSV lead ingestion
# --------------------------------------------------

def ingest_leads_csv(file_path, drop_name):
    file_path = Path(file_path)

    workflow_id = file_path.parent.name

    source_file = file_path.relative_to(BASE_DIR).as_posix()

    content_hash = file_hash(file_path)

    if file_already_ingested(
            drop_name,
            source_file,
            content_hash,
    ):
        return {
            "status": "already_ingested",
            "accepted": 0,
            "rejected": 0,
            "duplicates": 0,
            "warnings": 0,
        }

    schema = load_schema(workflow_id)
    fields = schema["fields"]

    batch_id = make_batch_id(
        drop_name,
        source_file,
        content_hash,
    )

    counts = {
        "accepted": 0,
        "rejected": 0,
        "duplicates": 0,
        "warnings": 0,
    }

    with file_path.open(
            "r",
            encoding="utf-8-sig",
            newline="",
    ) as file:

        reader = csv.DictReader(file)

        header_mapping = build_header_mapping(
            reader.fieldnames or [],
            fields,
            )

        for row_number, row in enumerate(reader, start=1):

            if not any(
                    str(value or "").strip()
                    for value in row.values()
            ):
                continue

            lead_data, rejection_reason, warnings = (
                parse_lead_row(
                    row,
                    fields,
                    header_mapping,
                )
            )

            if rejection_reason:
                save_rejection(
                    workflow_id,
                    source_file,
                    row_number,
                    rejection_reason,
                    row,
                )

                counts["rejected"] += 1
                continue

            result = upsert_lead(
                workflow_id,
                lead_data,
                batch_id,
            )

            if result == "inserted":
                counts["accepted"] += 1
            else:
                counts["duplicates"] += 1

            counts["warnings"] += warnings

            phone = lead_data.get("phone")

            if phone:
                link_orphan_events(
                    workflow_id,
                    phone,
                )

    record_file_ingestion(
        drop_name,
        source_file,
        content_hash,
        batch_id,
        counts,
    )

    return counts


# --------------------------------------------------
# JSONL event ingestion
# --------------------------------------------------

def ingest_events_jsonl(file_path, drop_name):
    file_path = Path(file_path)

    source_file = file_path.relative_to(BASE_DIR).as_posix()

    content_hash = file_hash(file_path)

    if file_already_ingested(
            drop_name,
            source_file,
            content_hash,
    ):
        return {
            "status": "already_ingested",
            "inserted": 0,
            "duplicates": 0,
        }

    batch_id = make_batch_id(
        drop_name,
        source_file,
        content_hash,
    )

    counts = process_jsonl(file_path)

    record_file_ingestion(
        drop_name,
        source_file,
        content_hash,
        batch_id,
        counts,
    )

    return counts


# --------------------------------------------------
# Complete drop ingestion
# --------------------------------------------------

def ingest_drop(drop_path):
    initialize_database()

    drop_path = Path(drop_path)

    if not drop_path.is_absolute():
        drop_path = BASE_DIR / drop_path

    drop_name = drop_path.name

    if not drop_path.exists():
        raise FileNotFoundError(
            f"Drop directory not found: {drop_path}"
        )

    results = {
        "drop": drop_name,
        "leads": [],
        "events": [],
    }

    # Process CSV files first so that leads are available
    # before event ingestion.

    csv_files = sorted(
        drop_path.glob("leads/**/*.csv")
    )

    for csv_file in csv_files:
        result = ingest_leads_csv(
            csv_file,
            drop_name,
        )

        results["leads"].append({
            "file": csv_file.name,
            "counts": result,
        })

    # Process event files after leads.

    event_files = sorted(
        drop_path.glob("events/*.jsonl")
    )

    for event_file in event_files:
        result = ingest_events_jsonl(
            event_file,
            drop_name,
        )

        results["events"].append({
            "file": event_file.name,
            "counts": result,
        })

    return results
