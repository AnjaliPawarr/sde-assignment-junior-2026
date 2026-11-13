
import csv
import json
from collections import defaultdict
from pathlib import Path

from app.config import BASE_DIR
from app.database import get_db, initialize_database
from app.security import decrypt_pii
from app.status import calculate_lead_status


SCHEMA_DIR = BASE_DIR / "assignment-a-data" / "schemas"


def load_workflow_schema(workflow_id):
    path = SCHEMA_DIR / f"{workflow_id}.json"

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def write_csv(path, columns, rows):
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=columns,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def get_lead_data(lead):
    """Read lead data and apply schema defaults to missing values."""

    data = json.loads(lead["non_pii_data"] or "{}")
    schema = load_workflow_schema(lead["workflow_id"])

    for field in schema["fields"]:
        name = field["name"]

        if data.get(name) is None and "default" in field:
            data[name] = field["default"]

    return data, schema


def build_lead_report(leads):
    rows = []
    statuses = {}

    for lead in leads:
        data, schema = get_lead_data(lead)

        reference_field = next(
            field["name"]
            for field in schema["fields"]
            if field.get("reference") is True
        )

        external_ref = data.get(reference_field, "")

        phone = decrypt_pii(lead["phone_encrypted"])
        phone_masked = "+91******" + phone[-4:]

        status = calculate_lead_status(lead["id"])
        statuses[lead["id"]] = status

        rows.append({
            "workflow_id": lead["workflow_id"],
            "external_ref": external_ref,
            "batch_id": lead["batch_id"],
            "phone_masked": phone_masked,
            "bucket": status["bucket"],
            "total_calls": status["total_calls"],
            "connected_calls": status["connected_calls"],
            "last_call_at": status["last_call_at"] or "",
            "current_disposition": (
                    status["current_disposition"] or ""
            ),
            "ever_success": str(status["ever_success"]).lower(),
        })

    rows.sort(
        key=lambda row: (
            row["workflow_id"],
            str(row["external_ref"]),
        )
    )

    return rows, statuses


def build_batch_summary(leads, statuses):
    grouped = defaultdict(lambda: {
        "total_leads": 0,
        "yet_to_reach_out": 0,
        "in_progress_telephony_failed": 0,
        "in_progress_dialed": 0,
        "completed": 0,
    })

    for lead in leads:
        key = (lead["workflow_id"], lead["batch_id"])
        bucket = statuses[lead["id"]]["bucket"]

        grouped[key]["total_leads"] += 1
        grouped[key][bucket] += 1

    rows = []

    for (workflow_id, batch_id), counts in sorted(grouped.items()):
        rows.append({
            "workflow_id": workflow_id,
            "batch_id": batch_id,
            **counts,
        })

    return rows


def build_daily_overview(leads, statuses):
    daily = {}

    for lead in leads:
        workflow_id = lead["workflow_id"]
        lead_id = lead["id"]

        for call in statuses[lead_id]["calls"]:
            key = (workflow_id, call["date"])

            if key not in daily:
                daily[key] = {
                    "total_calls": 0,
                    "connected_calls": 0,
                    "success_lead_ids": set(),
                }

            daily[key]["total_calls"] += 1

            if call["connected"]:
                daily[key]["connected_calls"] += 1

            if call["is_success"]:
                daily[key]["success_lead_ids"].add(lead_id)

    rows = []

    for (workflow_id, date), metrics in sorted(daily.items()):
        total = metrics["total_calls"]
        connected = metrics["connected_calls"]

        rows.append({
            "workflow_id": workflow_id,
            "date": date,
            "total_calls": total,
            "connected_calls": connected,
            "connectivity_rate": f"{connected / total:.4f}",
            "success_leads": len(metrics["success_lead_ids"]),
        })

    return rows


def build_rejections():
    with get_db() as db:
        records = db.execute(
            """
            SELECT workflow_id, source_file, row_number, reason
            FROM rejections
            """
        ).fetchall()

    rows = []

    for record in records:
        rows.append({
            "workflow_id": record["workflow_id"],
            "batch_id": Path(record["source_file"]).stem,
            "row_number": record["row_number"],
            "reason": record["reason"],
        })

    rows.sort(
        key=lambda row: (
            row["workflow_id"],
            row["batch_id"],
            row["row_number"],
        )
    )

    return rows


def build_data_quality():
    with get_db() as db:
        batches = db.execute(
            """
            SELECT source_file, counts_json
            FROM ingestion_batches
            """
        ).fetchall()

        rejection_counts = db.execute(
            """
            SELECT reason, COUNT(*) AS total
            FROM rejections
            GROUP BY reason
            ORDER BY reason
            """
        ).fetchall()

        orphan_count = db.execute(
            """
            SELECT COUNT(*)
            FROM interactions
            WHERE lead_id IS NULL
            """
        ).fetchone()[0]

    lead_rows_total = 0
    lead_rows_rejected = 0
    duplicate_lead_rows_merged = 0
    field_warnings = 0

    events_total = 0
    malformed_events = 0
    duplicate_events_dropped = 0
    unknown_disposition_events = 0

    for batch in batches:
        counts = json.loads(batch["counts_json"] or "{}")
        source_file = batch["source_file"].lower()

        if source_file.endswith(".csv"):
            accepted = counts.get("accepted", 0)
            rejected = counts.get("rejected", 0)
            duplicates = counts.get("duplicates", 0)

            lead_rows_total += accepted + rejected + duplicates
            lead_rows_rejected += rejected
            duplicate_lead_rows_merged += duplicates
            field_warnings += counts.get("warnings", 0)

        elif source_file.endswith(".jsonl"):
            events_total += sum(
                value
                for key, value in counts.items()
                if key != "blank_lines" and isinstance(value, int)
            )

            malformed_events += (
                    counts.get("malformed_json", 0)
                    + counts.get("missing_event_id", 0)
            )

            duplicate_events_dropped += counts.get(
                "duplicate_event", 0
            )

            unknown_disposition_events += counts.get(
                "unknown_disposition", 0
            )

    return {
        "lead_rows_total": lead_rows_total,
        "lead_rows_rejected": lead_rows_rejected,
        "rejections_by_reason": {
            row["reason"]: row["total"]
            for row in rejection_counts
        },
        "duplicate_lead_rows_merged": duplicate_lead_rows_merged,
        "field_warnings": field_warnings,
        "events_total": events_total,
        "malformed_events": malformed_events,
        "duplicate_events_dropped": duplicate_events_dropped,
        "orphan_events": orphan_count,
        "unknown_disposition_events": unknown_disposition_events,
    }


def generate_reports(output_dir):
    """Generate all five assignment reports."""

    initialize_database()

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with get_db() as db:
        leads = db.execute(
            """
            SELECT id, workflow_id, batch_id,
                   phone_encrypted, non_pii_data
            FROM leads
            WHERE batch_id NOT LIKE 'test_%'
            ORDER BY workflow_id, batch_id, id
            """
        ).fetchall()

    lead_rows, statuses = build_lead_report(leads)

    batch_rows = build_batch_summary(leads, statuses)
    daily_rows = build_daily_overview(leads, statuses)
    rejection_rows = build_rejections()
    quality = build_data_quality()

    write_csv(
        output_dir / "batch_summary.csv",
        [
            "workflow_id",
            "batch_id",
            "total_leads",
            "yet_to_reach_out",
            "in_progress_telephony_failed",
            "in_progress_dialed",
            "completed",
        ],
        batch_rows,
        )

    write_csv(
        output_dir / "daily_overview.csv",
        [
            "workflow_id",
            "date",
            "total_calls",
            "connected_calls",
            "connectivity_rate",
            "success_leads",
        ],
        daily_rows,
        )

    write_csv(
        output_dir / "lead_report.csv",
        [
            "workflow_id",
            "external_ref",
            "batch_id",
            "phone_masked",
            "bucket",
            "total_calls",
            "connected_calls",
            "last_call_at",
            "current_disposition",
            "ever_success",
        ],
        lead_rows,
        )

    write_csv(
        output_dir / "rejections.csv",
        [
            "workflow_id",
            "batch_id",
            "row_number",
            "reason",
        ],
        rejection_rows,
        )

    with (output_dir / "data_quality.json").open(
            "w",
            encoding="utf-8",
    ) as file:
        json.dump(quality, file, indent=2)

    return {
        "output_dir": str(output_dir),
        "leads": len(leads),
        "files": [
            "batch_summary.csv",
            "daily_overview.csv",
            "lead_report.csv",
            "rejections.csv",
            "data_quality.json",
        ],
    }
