
import sqlite3
import pytest

from app.database import SCHEMA
from app.status import calculate_lead_status


@pytest.fixture
def test_db(monkeypatch, tmp_path):
    """Use a separate temporary database for every test."""

    test_db_path = tmp_path / "test_ledger.sqlite3"

    def test_connection():
        connection = sqlite3.connect(test_db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    monkeypatch.setattr("app.database.get_connection", test_connection)

    with test_connection() as db:
        db.executescript(SCHEMA)
        db.execute(
            """
            INSERT INTO leads (
                id, workflow_id, phone_hmac, phone_encrypted,
                pii_data_encrypted, non_pii_data, batch_id,
                created_at, updated_at
            )
            VALUES (1, 'motor_renewal', 'test_hmac',
                    'encrypted', '{}', '{}', 'test_batch',
                    '2026-11-13', '2026-11-13')
            """
        )

    return 1


def add_event(lead_id, event_id, event_type, call_id, timestamp,
              disposition=None):
    from app.database import get_db

    with get_db() as db:
        db.execute(
            """
            INSERT INTO interactions (
                event_id, workflow_id, lead_id, phone_hmac,
                event_type, call_id, occurred_at,
                disposition, payload_encrypted, received_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id, "motor_renewal", lead_id, "test_hmac",
                event_type, call_id, timestamp,
                disposition, None, timestamp
            )
        )


def test_yet_to_reach_out(test_db):
    result = calculate_lead_status(test_db)
    assert result["bucket"] == "yet_to_reach_out"
    assert result["total_calls"] == 0


def test_in_progress_dialed(test_db):
    add_event(test_db, "ev1", "call.initiated", "call1",
              "2026-11-13T10:00:00+00:00")

    result = calculate_lead_status(test_db)
    assert result["bucket"] == "in_progress_dialed"
    assert result["total_calls"] == 1


def test_in_progress_telephony_failed(test_db):
    add_event(test_db, "ev2", "call.initiated", "call2",
              "2026-11-13T10:00:00+00:00")
    add_event(test_db, "ev3", "call.telephony_failed", "call2",
              "2026-11-13T10:01:00+00:00")

    result = calculate_lead_status(test_db)
    assert result["bucket"] == "in_progress_telephony_failed"


def test_completed_and_success(test_db):
    add_event(test_db, "ev4", "call.initiated", "call3",
              "2026-11-13T10:00:00+00:00")
    add_event(test_db, "ev5", "disposition.set", "call3",
              "2026-11-13T10:02:00+00:00", "renewed")

    result = calculate_lead_status(test_db)
    assert result["bucket"] == "completed"
    assert result["ever_success"] is True


def test_latest_override_wins(test_db):
    add_event(test_db, "ev6", "call.initiated", "call4",
              "2026-11-13T10:00:00+00:00")
    add_event(test_db, "ev7", "disposition.set", "call4",
              "2026-11-13T10:01:00+00:00", "renewed")
    add_event(test_db, "ev8", "disposition.override", "call4",
              "2026-11-13T10:02:00+00:00", "not_interested")

    result = calculate_lead_status(test_db)
    assert result["current_disposition"] == "not_interested"
    assert result["bucket"] == "completed"
    assert result["ever_success"] is False
