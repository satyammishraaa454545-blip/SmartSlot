"""Timetable version storage.

Functions here are *primitives*: they never open a transaction themselves.
Callers (``services.versions``) wrap multi-step changes in
``db.transaction`` so that nothing is ever half-saved.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any, Optional

from ..db import utc_now
from ..engine.models import Entry, UnscheduledItem


@dataclass
class UnscheduledNote:
    """Stored explanation for a session that is not on the timetable."""

    session_id: str
    reasons: list[str]
    reason_codes: list[str]
    hints: list[str]


def next_seq(conn: sqlite3.Connection, dataset_id: int) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(seq), 0) + 1 AS n FROM timetable_versions WHERE dataset_id = ?", (dataset_id,)
    ).fetchone()
    return int(row["n"])


def insert_version(
    conn: sqlite3.Connection,
    *,
    dataset_id: int,
    label: Optional[str],
    source: str,
    created_by: str,
    parent_version_id: Optional[int],
    notes: str,
    is_complete: bool,
    generation_result: Optional[dict[str, Any]],
) -> tuple[int, int, str]:
    """Insert a DRAFT version row.  Returns ``(version_id, seq, label)``."""
    seq = next_seq(conn, dataset_id)
    final_label = (label or "").strip() or f"Version {seq}"
    cur = conn.execute(
        "INSERT INTO timetable_versions (dataset_id, seq, status, label, source, created_at, created_by, "
        "is_complete, parent_version_id, notes, generation_result) VALUES (?, ?, 'draft', ?, ?, ?, ?, ?, ?, ?, ?)",
        (dataset_id, seq, final_label, source, utc_now(), created_by, int(is_complete), parent_version_id, notes,
         json.dumps(generation_result) if generation_result is not None else None),
    )
    return int(cur.lastrowid or 0), seq, final_label


def get_row(conn: sqlite3.Connection, version_id: int) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM timetable_versions WHERE id = ?", (version_id,)).fetchone()


def list_rows(conn: sqlite3.Connection, dataset_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM timetable_versions WHERE dataset_id = ? ORDER BY seq DESC", (dataset_id,)
    ).fetchall()


def published_row(conn: sqlite3.Connection, dataset_id: int) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM timetable_versions WHERE dataset_id = ? AND status = 'published'", (dataset_id,)
    ).fetchone()


def version_count(conn: sqlite3.Connection, dataset_id: int) -> int:
    return int(conn.execute(
        "SELECT COUNT(*) AS n FROM timetable_versions WHERE dataset_id = ?", (dataset_id,)
    ).fetchone()["n"])


# -- entries -----------------------------------------------------------------
def insert_entries(conn: sqlite3.Connection, version_id: int, entries: list[Entry]) -> None:
    conn.executemany(
        "INSERT INTO timetable_entries VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [(version_id, e.session_id, e.day, e.start_period, e.duration, e.teacher_id, e.room_id,
          e.subject_id, e.batch_id) for e in entries],
    )


def load_entries(conn: sqlite3.Connection, version_id: int) -> list[Entry]:
    """Entries in insertion order (the API layer sorts them for display)."""
    rows = conn.execute(
        "SELECT * FROM timetable_entries WHERE version_id = ? ORDER BY rowid", (version_id,)
    ).fetchall()
    return [Entry(session_id=r["session_id"], day=r["day"], start_period=r["start_period"],
                  duration=r["duration"], teacher_id=r["teacher_id"], room_id=r["room_id"],
                  subject_id=r["subject_id"], batch_id=r["batch_id"]) for r in rows]


def replace_entry(conn: sqlite3.Connection, version_id: int, entry: Entry) -> None:
    conn.execute(
        "UPDATE timetable_entries SET day = ?, start_period = ?, duration = ?, teacher_id = ?, room_id = ? "
        "WHERE version_id = ? AND session_id = ?",
        (entry.day, entry.start_period, entry.duration, entry.teacher_id, entry.room_id, version_id, entry.session_id),
    )


def delete_entry(conn: sqlite3.Connection, version_id: int, session_id: str) -> None:
    conn.execute("DELETE FROM timetable_entries WHERE version_id = ? AND session_id = ?", (version_id, session_id))


# -- unscheduled notes ----------------------------------------------------------
def insert_unscheduled(conn: sqlite3.Connection, version_id: int, items: list[UnscheduledNote]) -> None:
    base = int(conn.execute(
        "SELECT COALESCE(MAX(position), -1) + 1 AS n FROM version_unscheduled WHERE version_id = ?", (version_id,)
    ).fetchone()["n"])
    conn.executemany(
        "INSERT OR REPLACE INTO version_unscheduled VALUES (?, ?, ?, ?, ?, ?)",
        [(version_id, it.session_id, base + i, json.dumps(it.reasons), json.dumps(it.reason_codes),
          json.dumps(it.hints)) for i, it in enumerate(items)],
    )


def notes_from_result(items: list[UnscheduledItem]) -> list[UnscheduledNote]:
    return [UnscheduledNote(i.session.session_id, i.reasons, i.reason_codes, i.hints) for i in items]


def delete_unscheduled(conn: sqlite3.Connection, version_id: int, session_id: str) -> None:
    conn.execute("DELETE FROM version_unscheduled WHERE version_id = ? AND session_id = ?", (version_id, session_id))


def load_unscheduled_notes(conn: sqlite3.Connection, version_id: int) -> dict[str, UnscheduledNote]:
    rows = conn.execute(
        "SELECT * FROM version_unscheduled WHERE version_id = ? ORDER BY position", (version_id,)
    ).fetchall()
    return {
        r["session_id"]: UnscheduledNote(
            r["session_id"], json.loads(r["reasons"]), json.loads(r["reason_codes"]), json.loads(r["hints"])
        )
        for r in rows
    }


# -- status changes ---------------------------------------------------------------
def archive_published(conn: sqlite3.Connection, dataset_id: int) -> None:
    conn.execute(
        "UPDATE timetable_versions SET status = 'archived' WHERE dataset_id = ? AND status = 'published'",
        (dataset_id,),
    )


def mark_published(conn: sqlite3.Connection, version_id: int, is_complete: bool) -> None:
    conn.execute(
        "UPDATE timetable_versions SET status = 'published', published_at = ?, is_complete = ? WHERE id = ?",
        (utc_now(), int(is_complete), version_id),
    )


def set_complete(conn: sqlite3.Connection, version_id: int, is_complete: bool) -> None:
    conn.execute("UPDATE timetable_versions SET is_complete = ? WHERE id = ?", (int(is_complete), version_id))


def delete_version(conn: sqlite3.Connection, version_id: int) -> None:
    conn.execute("DELETE FROM timetable_versions WHERE id = ?", (version_id,))
