
import os
from pathlib import Path
from zoneinfo import ZoneInfo

# Project root directory
# config.py -> app -> solution -> project root
BASE_DIR = Path(__file__).resolve().parents[2]

# Input and output directories
DATA_DIR = BASE_DIR / "data"
REPORTS_DIR = BASE_DIR / "reports"

# SQLite database location
DB_PATH = BASE_DIR / "solution" / "interaction_ledger.sqlite3"

# Reporting timezone
IST = ZoneInfo("Asia/Kolkata")

# Security: secrets must come from environment variables.
PII_ENCRYPTION_KEY = os.getenv("PII_ENCRYPTION_KEY")
PII_HMAC_KEY = os.getenv("PII_HMAC_KEY")
