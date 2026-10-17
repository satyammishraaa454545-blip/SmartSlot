"""SQLite access: connection factory, schema (create-if-not-exists) and transactions.

Plain ``sqlite3`` is used on purpose.  The schema is tiny and migrations are
"create if not exists", so there is nothing to run by hand: the database file
and its directory are created on first use.

Connections run in autocommit mode (``isolation_level=None``); multi-row writes
go through :func:`transaction`, which opens ``BEGIN IMMEDIATE`` and either
commits everything or rolls everything back.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from . import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS datasets (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    semester      TEXT NOT NULL DEFAULT '',
    source        TEXT NOT NULL DEFAULT 'upload',
    import_status TEXT NOT NULL CHECK (import_status IN ('ok', 'has_errors')),
    import_report TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS teachers (
    dataset_id    INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    teacher_id    TEXT NOT NULL,
    name          TEXT NOT NULL,
    department_id TEXT NOT NULL DEFAULT '',
    position      INTEGER NOT NULL,
    PRIMARY KEY (dataset_id, teacher_id)
);

CREATE TABLE IF NOT EXISTS subjects (
    dataset_id    INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    subject_id    TEXT NOT NULL,
    name          TEXT NOT NULL,
    department_id TEXT NOT NULL DEFAULT '',
    session_type  TEXT NOT NULL CHECK (session_type IN ('lecture', 'practical')),
    position      INTEGER NOT NULL,
    PRIMARY KEY (dataset_id, subject_id)
);

CREATE TABLE IF NOT EXISTS batches (
    dataset_id    INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    batch_id      TEXT NOT NULL,
    name          TEXT NOT NULL,
    semester      TEXT NOT NULL DEFAULT '',
    student_count INTEGER NOT NULL CHECK (student_count >= 1),
    department_id TEXT NOT NULL DEFAULT '',
    position      INTEGER NOT NULL,
    PRIMARY KEY (dataset_id, batch_id)
);

CREATE TABLE IF NOT EXISTS rooms (
    dataset_id INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    room_id    TEXT NOT NULL,
    name       TEXT NOT NULL,
    capacity   INTEGER NOT NULL CHECK (capacity >= 1),
    room_type  TEXT NOT NULL CHECK (room_type IN ('classroom', 'lab')),
    position   INTEGER NOT NULL,
    PRIMARY KEY (dataset_id, room_id)
);

CREATE TABLE IF NOT EXISTS requirements (
    dataset_id        INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    subject_id        TEXT NOT NULL,
    batch_id          TEXT NOT NULL,
    teacher_id        TEXT NOT NULL,
    sessions_per_week INTEGER NOT NULL CHECK (sessions_per_week >= 1),
    duration          INTEGER NOT NULL DEFAULT 1 CHECK (duration >= 1),
    position          INTEGER NOT NULL,
    PRIMARY KEY (dataset_id, subject_id, batch_id, teacher_id)
);

CREATE TABLE IF NOT EXISTS days (
    dataset_id INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    day        TEXT NOT NULL,
    position   INTEGER NOT NULL,
    PRIMARY KEY (dataset_id, day)
);

CREATE TABLE IF NOT EXISTS periods (
    dataset_id INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    period     INTEGER NOT NULL CHECK (period >= 1),
    start_time TEXT NOT NULL,
    end_time   TEXT NOT NULL,
    is_break   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (dataset_id, period)
);

-- Only "not available" rules are stored (available is the default).
CREATE TABLE IF NOT EXISTS availability (
    dataset_id  INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    resource_id TEXT NOT NULL,
    day         TEXT NOT NULL,
    period      INTEGER NOT NULL,
    available   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (dataset_id, resource_id, day, period)
);

CREATE TABLE IF NOT EXISTS timetable_versions (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_id        INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    seq               INTEGER NOT NULL,
    status            TEXT NOT NULL CHECK (status IN ('draft', 'published', 'archived')),
    label             TEXT NOT NULL,
    source            TEXT NOT NULL DEFAULT 'generated',
    created_at        TEXT NOT NULL,
    created_by        TEXT NOT NULL DEFAULT 'coordinator',
    published_at      TEXT,
    is_complete       INTEGER NOT NULL DEFAULT 0,
    parent_version_id INTEGER REFERENCES timetable_versions(id) ON DELETE SET NULL,
    notes             TEXT NOT NULL DEFAULT '',
    generation_result TEXT,
    UNIQUE (dataset_id, seq)
);
-- At most one published version per dataset.
CREATE UNIQUE INDEX IF NOT EXISTS one_published_per_dataset
    ON timetable_versions(dataset_id) WHERE status = 'published';

CREATE TABLE IF NOT EXISTS timetable_entries (
    version_id   INTEGER NOT NULL REFERENCES timetable_versions(id) ON DELETE CASCADE,
    session_id   TEXT NOT NULL,
    day          TEXT NOT NULL,
    start_period INTEGER NOT NULL,
    duration     INTEGER NOT NULL,
    teacher_id   TEXT NOT NULL,
    room_id      TEXT NOT NULL,
    subject_id   TEXT NOT NULL,
    batch_id     TEXT NOT NULL,
    PRIMARY KEY (version_id, session_id)
);

CREATE TABLE IF NOT EXISTS version_unscheduled (
    version_id   INTEGER NOT NULL REFERENCES timetable_versions(id) ON DELETE CASCADE,
    session_id   TEXT NOT NULL,
    position     INTEGER NOT NULL,
    reasons      TEXT NOT NULL,
    reason_codes TEXT NOT NULL,
    hints        TEXT NOT NULL,
    PRIMARY KEY (version_id, session_id)
);
"""

_init_lock = threading.Lock()
_initialised: set[str] = set()


def utc_now() -> str:
    """ISO-8601 UTC timestamp with a ``Z`` suffix, e.g. ``2026-10-16T09:30:00Z``."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ensure_schema(path: Path) -> None:
    """Create the directory, the file and all tables (idempotent, once per path)."""
    key = str(path.resolve())
    if key in _initialised and path.exists():
        return
    with _init_lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, timeout=15, isolation_level=None)
        try:
            try:
                conn.execute("PRAGMA journal_mode=WAL")
            except sqlite3.DatabaseError:  # e.g. network drive: keep the default journal
                pass
            conn.executescript(SCHEMA)
        finally:
            conn.close()
        _initialised.add(key)


def init_db() -> Path:
    """Create the database if needed and return its path."""
    path = settings.db_path()
    ensure_schema(path)
    return path


def connect() -> sqlite3.Connection:
    path = init_db()
    # check_same_thread=False: FastAPI may create the connection in one worker
    # thread and use it in another; a connection is never shared between requests.
    conn = sqlite3.connect(path, timeout=15, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=15000")
    return conn


def get_conn() -> Iterator[sqlite3.Connection]:
    """FastAPI dependency: one connection per request."""
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """All-or-nothing write block (takes the write lock immediately)."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def wipe_all(conn: sqlite3.Connection) -> None:
    """Delete every dataset (cascades to everything) and restart id counters."""
    with transaction(conn):
        conn.execute("DELETE FROM datasets")
        conn.execute(
            "DELETE FROM sqlite_sequence WHERE name IN ('datasets', 'timetable_versions')"
        )
