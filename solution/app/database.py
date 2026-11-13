
import sqlite3
from contextlib import contextmanager

from app.config import DB_PATH


SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id TEXT NOT NULL,
    phone_hmac TEXT NOT NULL,
    phone_encrypted TEXT NOT NULL,
    pii_data_encrypted TEXT NOT NULL DEFAULT '{}',
    non_pii_data TEXT NOT NULL DEFAULT '{}',
    batch_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    UNIQUE(workflow_id, phone_hmac)
);

CREATE TABLE IF NOT EXISTS interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    workflow_id TEXT NOT NULL,
    lead_id INTEGER,
    phone_hmac TEXT,
    event_type TEXT NOT NULL,
    call_id TEXT,
    occurred_at TEXT NOT NULL,
    disposition TEXT,
    payload_encrypted TEXT,
    received_at TEXT NOT NULL,

    FOREIGN KEY(lead_id) REFERENCES leads(id)
);

CREATE TABLE IF NOT EXISTS rejections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id TEXT NOT NULL,
    source_file TEXT NOT NULL,
    row_number INTEGER NOT NULL,
    reason TEXT NOT NULL,
    row_data_encrypted TEXT,
    rejected_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ingestion_batches (
    id TEXT PRIMARY KEY,
    drop_name TEXT NOT NULL,
    source_file TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    ingested_at TEXT NOT NULL,
    counts_json TEXT NOT NULL DEFAULT '{}',

    UNIQUE(drop_name, source_file, content_hash)
);

CREATE TABLE IF NOT EXISTS ingested_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    drop_name TEXT NOT NULL,
    source_file TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    ingested_at TEXT NOT NULL,

    UNIQUE(drop_name, source_file, content_hash),
    FOREIGN KEY(batch_id) REFERENCES ingestion_batches(id)
);

CREATE INDEX IF NOT EXISTS idx_leads_workflow
ON leads(workflow_id);

CREATE INDEX IF NOT EXISTS idx_interactions_lead
ON interactions(lead_id);

CREATE INDEX IF NOT EXISTS idx_interactions_call
ON interactions(call_id);

CREATE INDEX IF NOT EXISTS idx_interactions_time
ON interactions(occurred_at);

CREATE INDEX IF NOT EXISTS idx_interactions_phone
ON interactions(workflow_id, phone_hmac);
"""


def get_connection():
    """Create a SQLite connection with foreign keys enabled."""

    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")

    return connection


@contextmanager
def get_db():
    """Provide a connection and manage transaction commit/rollback."""

    connection = get_connection()

    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database():
    """Create database tables and indexes if they do not exist."""

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    with get_db() as connection:
        connection.executescript(SCHEMA)


def check_database():
    """Return names of all created tables."""

    with get_db() as connection:
        rows = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            ORDER BY name
            """
        ).fetchall()

    return [row["name"] for row in rows]
