
from datetime import datetime

from app.config import IST
from app.database import get_db
from app.events import load_dispositions


def calculate_lead_status(lead_id):
    """Calculate lead status using call-level effective dispositions."""

    with get_db() as db:
        lead = db.execute(
            "SELECT workflow_id FROM leads WHERE id = ?",
            (lead_id,),
        ).fetchone()

        if not lead:
            raise ValueError(f"Lead not found: {lead_id}")

        events = db.execute(
            """
            SELECT event_type, call_id, occurred_at, disposition
            FROM interactions
            WHERE lead_id = ? AND call_id IS NOT NULL
            ORDER BY occurred_at ASC, id ASC
            """,
            (lead_id,),
        ).fetchall()

    workflow_id = lead["workflow_id"]
    rules = load_dispositions()

    calls = {}

    # Group all events by call_id, regardless of arrival order.
    for event in events:
        call_id = event["call_id"]
        calls.setdefault(call_id, []).append(event)

    call_results = []

    for call_id, call_events in calls.items():

        initiated = [
            e for e in call_events
            if e["event_type"] == "call.initiated"
        ]

        # A call counts only when call.initiated exists.
        if not initiated:
            continue

        initiated.sort(key=lambda e: (e["occurred_at"], e["call_id"]))
        initiated_event = initiated[-1]

        overrides = [
            e for e in call_events
            if e["event_type"] == "disposition.override"
        ]

        dispositions = [
            e for e in call_events
            if e["event_type"] == "disposition.set"
        ]

        # Latest override wins; otherwise latest disposition.set.
        selected = (
            overrides[-1] if overrides
            else dispositions[-1] if dispositions
            else None
        )

        disposition = selected["disposition"] if selected else None
        rule = rules.get((workflow_id, disposition), {})

        initiated_dt = datetime.fromisoformat(
            initiated_event["occurred_at"].replace("Z", "+00:00")
        )

        if initiated_dt.tzinfo is None:
            initiated_dt = initiated_dt.replace(tzinfo=IST)

        initiated_ist = initiated_dt.astimezone(IST)

        call_results.append({
            "call_id": call_id,
            "initiated_at": initiated_dt.isoformat(),
            "initiated_at_ist": initiated_ist.isoformat(),
            "date": initiated_ist.date().isoformat(),
            "connected": any(
                e["event_type"] == "call.connected"
                for e in call_events
            ),
            "failed": any(
                e["event_type"] == "call.telephony_failed"
                for e in call_events
            ),
            "effective_disposition": disposition,
            "is_terminal": bool(rule.get("is_terminal", False)),
            "is_success": bool(rule.get("is_success", False)),
        })

    call_results.sort(key=lambda c: c["initiated_at"])

    total_calls = len(call_results)
    connected_calls = sum(c["connected"] for c in call_results)

    completed = any(c["is_terminal"] for c in call_results)
    ever_success = any(c["is_success"] for c in call_results)

    calls_with_disposition = [
        c for c in call_results
        if c["effective_disposition"] is not None
    ]

    current_disposition = (
        calls_with_disposition[-1]["effective_disposition"]
        if calls_with_disposition else None
    )

    last_call_at = (
        call_results[-1]["initiated_at_ist"]
        if call_results else None
    )

    if total_calls == 0:
        bucket = "yet_to_reach_out"
    elif completed:
        bucket = "completed"
    elif all(c["failed"] for c in call_results):
        bucket = "in_progress_telephony_failed"
    else:
        bucket = "in_progress_dialed"

    return {
        "lead_id": lead_id,
        "total_calls": total_calls,
        "connected_calls": connected_calls,
        "effective_disposition": current_disposition,
        "is_terminal": completed,
        "is_success": ever_success,
        "bucket": bucket,
        "last_call_at": last_call_at,
        "current_disposition": current_disposition,
        "ever_success": ever_success,
        "calls": call_results,
    }
