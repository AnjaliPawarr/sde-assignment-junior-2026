# Submission

## Candidate
- **Name:** Anjali Pawar
- **Assignment chosen:** A (Interaction Ledger & Reporting Pipeline)
- **Time spent:** [Enter your actual approximate time]

## How to run

### Prerequisites
- Python 3.11 or later
- Windows PowerShell (commands below use PowerShell)
- Git

### 1. Clone the repository
```bash
git clone https://github.com/AryamannNingombam/sde-assignment-junior-2026.git
cd sde-assignment-junior-2026
```

### 2. Create and activate a virtual environment
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Install dependencies
```powershell
pip install -r requirements.txt
```

### 4. Configure environment variables

Configure the following environment variables securely before running the application:
- `PII_ENCRYPTION_KEY`
- `PII_HMAC_KEY`

Do not commit secret keys to the repository.

### 5. Generate sample data
```powershell
python assignment-a-data\tools\generate_data.py --seed 42 --scale small --out data
```

### 6. Configure Python module path
```powershell
$env:PYTHONPATH = "$PWD\solution"
```

### 7. Ingest both data drops
```powershell
python -m app.cli ingest data/drop_1
python -m app.cli ingest data/drop_2
```

### 8. Generate reports
```powershell
python -m app.cli report --out reports/
```

### 9. Run tests
```powershell
pytest -v
```

## Design

The application is implemented in Python using SQLite as its persistent database.

### Architecture

The implementation is divided into modules:

- `config.py`: Application paths, database configuration, timezone and environment settings.
- `database.py`: SQLite connection management and database schema initialization.
- `normalization.py`: Phone number, date and numeric field normalization.
- `security.py`: PII encryption and deterministic HMAC generation.
- `leads.py`: Lead insertion and duplicate merging.
- `events.py`: Event parsing, validation, deduplication and orphan event linking.
- `status.py`: Effective disposition and lead status calculation.
- `ingestion.py`: CSV and JSONL ingestion, schema-driven validation, rejection handling and file tracking.
- `reports.py`: Generation of the five required reports.
- `cli.py`: Command-line interface for ingestion and report generation.

### Database design

The SQLite database contains the following main tables:

- `leads`: Stores lead records, workflow IDs, encrypted PII, non-PII data and batch information.
- `interactions`: Stores interaction events with unique event IDs, timestamps, call IDs and dispositions.
- `rejections`: Stores rejected input rows with encrypted row data and rejection reasons.
- `ingestion_batches`: Tracks ingestion batch metadata and processing counts.
- `ingested_files`: Tracks processed files using their content hashes to support idempotent ingestion.

### PII protection

- Phone numbers are normalized into a canonical Indian phone number format.
- Phone numbers are stored using deterministic HMAC values for matching and duplicate detection.
- Personally identifiable information is encrypted using Fernet encryption.
- Reports display masked phone numbers instead of raw phone numbers.

### Event processing and lead status

Events are stored in an append-only interaction ledger. Duplicate event IDs are ignored. Events that cannot initially be linked to a lead are retained as orphan events and can be linked when the corresponding lead becomes available.

Effective dispositions are calculated using the latest override when available; otherwise, the latest disposition set event is used.

Lead status is calculated using call events and the effective disposition:
- `yet_to_reach_out`
- `in_progress_dialed`
- `in_progress_telephony_failed`
- `completed`

### Reporting

The application generates exactly five reports:
1. `batch_summary.csv`
2. `daily_overview.csv`
3. `lead_report.csv`
4. `rejections.csv`
5. `data_quality.json`

Timestamps are interpreted and reported using the Asia/Kolkata timezone.

## Decisions & assumptions

| Decision | Why | Alternative considered |
|---|---|---|
| SQLite for persistence | Simple local setup and sufficient for the assignment data volume | PostgreSQL |
| Canonical Indian phone format | Consistent matching across different phone number formats | Store original formats |
| HMAC for phone matching | Enables deterministic matching without storing raw phone numbers | Plain-text phone indexing |
| Fernet encryption for PII | Protects sensitive information at rest | Plain-text storage |
| Content-hash-based file tracking | Prevents reprocessing unchanged files | Tracking by filename only |
| Latest override takes precedence | Ensures the latest override determines the effective disposition | Always use the latest set event |
| IST for report dates | Keeps reporting dates consistent with the requested timezone | UTC-only reporting |
| Defaults applied in report generation | Ensures missing values can be represented consistently in the output | Store defaults directly during ingestion |

## Failure modes considered

- Invalid CSV rows are rejected with a recorded reason.
- Invalid phone numbers and missing required fields are handled through validation.
- Malformed JSONL records are skipped and counted.
- Duplicate event IDs are ignored.
- Unknown dispositions are ignored and counted.
- Orphan events are retained for later linking.
- Repeated ingestion of unchanged files is skipped using file hashes.
- PII is encrypted before storage.
- Missing or invalid timestamps are handled during event validation.

Known limitations:
- The current implementation uses SQLite and is intended for local assignment execution.
- Database crash recovery and fully atomic processing of an entire input file could be strengthened.
- Additional integration and failure-injection tests would improve confidence in recovery scenarios.

## Testing

The automated test suite contains 25 passing tests.

Coverage includes:
- Valid and invalid phone number normalization.
- Date normalization and invalid date handling.
- Lead status bucket calculations.
- Effective disposition and latest override precedence.
- Deterministic batch ID generation.

Manual verification:
- Ingested both `drop_1` and `drop_2`.
- Re-ran both drops and confirmed that existing files were reported as `already_ingested`.
- Verified that database counts remained unchanged after repeated ingestion.
- Verified CLI help and report generation.
- Confirmed that all five required report files were generated.

## Results

Final report generation completed successfully.

- Leads included in reports: **1,892**
- Automated tests: **25 passed**
- Required report files generated: **5**
- Database counts after ingestion:
    - Leads: 1,894
    - Interactions: 8,331
    - Rejections: 108
    - Tracked files: 8

Two manually created test leads are excluded from the generated lead reports.

## If I had another day

1. Add more end-to-end integration tests for ingestion and report generation.
2. Improve transaction handling and recovery after interrupted file processing.
3. Add performance testing for larger data drops.
4. Improve structured logging and error diagnostics.
5. Add PostgreSQL support for production-scale usage.