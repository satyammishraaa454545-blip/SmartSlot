"""Central limits and paths (everything tunable lives here)."""

from __future__ import annotations

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent

# --- upload / import limits -------------------------------------------------
MAX_FILE_BYTES = 2 * 1024 * 1024  # per CSV file (also per file inside a zip)
MAX_UPLOAD_FILES = 24  # files in one multipart request
MAX_ZIP_MEMBERS = 40  # entries inside one zip
MAX_ZIP_TOTAL_BYTES = 12 * 1024 * 1024  # uncompressed bytes read from one zip
MAX_CSV_ROWS = 20_000  # data rows per file
MAX_ISSUES_PER_FILE = 200  # stored issues per file (counts stay exact)

# --- request limits ---------------------------------------------------------
MAX_UPLOAD_REQUEST_BYTES = 16 * 1024 * 1024  # multipart import requests
MAX_JSON_REQUEST_BYTES = 1 * 1024 * 1024  # every other request body

# --- CORS -------------------------------------------------------------------
CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


def db_path() -> Path:
    """SQLite file. Read from the environment on every call so tests can redirect it."""
    override = os.environ.get("SMARTSLOT_DB")
    return Path(override) if override else BACKEND_DIR / "data" / "smartslot.db"


def sample_dir() -> Path:
    override = os.environ.get("SMARTSLOT_SAMPLE_DIR")
    return Path(override) if override else REPO_ROOT / "sample_data"


def dev_mode() -> bool:
    return os.environ.get("SMARTSLOT_DEV") == "1"
