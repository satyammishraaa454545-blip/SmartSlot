"""Dataset storage: save an imported dataset, rebuild the engine ``Dataset``, edit config."""

from __future__ import annotations

import json
import sqlite3
from typing import Optional

from ..db import transaction, utc_now
from ..engine.models import AvailabilityRule, Config, Dataset, PeriodDef
from ..engine.models import Batch, Requirement, Room, Subject, Teacher
from ..importer.report import ImportReport


def insert_dataset(
    conn: sqlite3.Connection, *, name: str, semester: str, source: str, dataset: Dataset, report: ImportReport
) -> int:
    """Store a dataset with all its rows in ONE transaction (all or nothing)."""
    now = utc_now()
    with transaction(conn):
        cur = conn.execute(
            "INSERT INTO datasets (name, semester, source, import_status, import_report, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (name, semester, source, report.status, report.model_dump_json(), now, now),
        )
        did = int(cur.lastrowid or 0)
        conn.executemany(
            "INSERT INTO teachers VALUES (?, ?, ?, ?, ?)",
            [(did, t.teacher_id, t.name, t.department_id, i) for i, t in enumerate(dataset.teachers)],
        )
        conn.executemany(
            "INSERT INTO subjects VALUES (?, ?, ?, ?, ?, ?)",
            [(did, s.subject_id, s.name, s.department_id, s.session_type, i) for i, s in enumerate(dataset.subjects)],
        )
        conn.executemany(
            "INSERT INTO batches VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(did, b.batch_id, b.name, b.semester, b.student_count, b.department_id, i)
             for i, b in enumerate(dataset.batches)],
        )
        conn.executemany(
            "INSERT INTO rooms VALUES (?, ?, ?, ?, ?, ?)",
            [(did, r.room_id, r.name, r.capacity, r.room_type, i) for i, r in enumerate(dataset.rooms)],
        )
        conn.executemany(
            "INSERT INTO requirements VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(did, q.subject_id, q.batch_id, q.teacher_id, q.sessions_per_week, q.duration, i)
             for i, q in enumerate(dataset.requirements)],
        )
        _write_config(conn, did, dataset.config)
        _write_availability(conn, did, dataset.availability)
    return did


def _write_config(conn: sqlite3.Connection, did: int, config: Config) -> None:
    conn.execute("DELETE FROM days WHERE dataset_id = ?", (did,))
    conn.execute("DELETE FROM periods WHERE dataset_id = ?", (did,))
    conn.executemany("INSERT INTO days VALUES (?, ?, ?)", [(did, d, i) for i, d in enumerate(config.days)])
    conn.executemany(
        "INSERT INTO periods VALUES (?, ?, ?, ?, ?)",
        [(did, p.period, p.start, p.end, int(p.is_break)) for p in config.periods],
    )


def _write_availability(conn: sqlite3.Connection, did: int, rules: list[AvailabilityRule]) -> None:
    conn.execute("DELETE FROM availability WHERE dataset_id = ?", (did,))
    conn.executemany(
        "INSERT OR IGNORE INTO availability VALUES (?, ?, ?, ?, 0)",
        [(did, r.resource_id, r.day, r.period) for r in rules if not r.available],
    )


def get_row(conn: sqlite3.Connection, dataset_id: int) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM datasets WHERE id = ?", (dataset_id,)).fetchone()


def list_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Newest first; id breaks ties so the order is deterministic."""
    return conn.execute("SELECT * FROM datasets ORDER BY created_at DESC, id DESC").fetchall()


def report_of(row: sqlite3.Row) -> ImportReport:
    return ImportReport.model_validate(json.loads(row["import_report"]))


def load_dataset(conn: sqlite3.Connection, dataset_id: int) -> Dataset:
    """Rebuild the engine ``Dataset`` (rows come back in file order)."""
    row = get_row(conn, dataset_id)
    if row is None:
        raise KeyError(dataset_id)
    q = lambda sql: conn.execute(sql, (dataset_id,)).fetchall()  # noqa: E731
    periods = [
        PeriodDef(period=r["period"], start=r["start_time"], end=r["end_time"], is_break=bool(r["is_break"]))
        for r in q("SELECT * FROM periods WHERE dataset_id = ? ORDER BY period")
    ]
    return Dataset(
        name=row["name"],
        semester=row["semester"],
        teachers=[Teacher(teacher_id=r["teacher_id"], name=r["name"], department_id=r["department_id"])
                  for r in q("SELECT * FROM teachers WHERE dataset_id = ? ORDER BY position")],
        subjects=[Subject(subject_id=r["subject_id"], name=r["name"], department_id=r["department_id"],
                          session_type=r["session_type"])
                  for r in q("SELECT * FROM subjects WHERE dataset_id = ? ORDER BY position")],
        batches=[Batch(batch_id=r["batch_id"], name=r["name"], semester=r["semester"],
                       student_count=r["student_count"], department_id=r["department_id"])
                 for r in q("SELECT * FROM batches WHERE dataset_id = ? ORDER BY position")],
        rooms=[Room(room_id=r["room_id"], name=r["name"], capacity=r["capacity"], room_type=r["room_type"])
               for r in q("SELECT * FROM rooms WHERE dataset_id = ? ORDER BY position")],
        requirements=[Requirement(subject_id=r["subject_id"], batch_id=r["batch_id"], teacher_id=r["teacher_id"],
                                  sessions_per_week=r["sessions_per_week"], duration=r["duration"])
                      for r in q("SELECT * FROM requirements WHERE dataset_id = ? ORDER BY position")],
        availability=[AvailabilityRule(resource_id=r["resource_id"], day=r["day"], period=r["period"], available=False)
                      for r in q("SELECT * FROM availability WHERE dataset_id = ? "
                                 "ORDER BY resource_id, day, period")],
        config=Config(days=[r["day"] for r in q("SELECT * FROM days WHERE dataset_id = ? ORDER BY position")],
                      periods=periods),
    )


def delete_dataset(conn: sqlite3.Connection, dataset_id: int) -> None:
    with transaction(conn):
        conn.execute("DELETE FROM datasets WHERE id = ?", (dataset_id,))


def _touch(conn: sqlite3.Connection, dataset_id: int) -> None:
    conn.execute("UPDATE datasets SET updated_at = ? WHERE id = ?", (utc_now(), dataset_id))


def replace_config(conn: sqlite3.Connection, dataset_id: int, config: Config) -> None:
    with transaction(conn):
        _write_config(conn, dataset_id, config)
        _touch(conn, dataset_id)


def replace_availability(conn: sqlite3.Connection, dataset_id: int, rules: list[AvailabilityRule]) -> None:
    with transaction(conn):
        _write_availability(conn, dataset_id, rules)
        _touch(conn, dataset_id)


def set_unavailable(
    conn: sqlite3.Connection, dataset_id: int, changes: list[tuple[str, str, int, bool]]
) -> int:
    """Apply ``(resource, day, period, available)`` toggles atomically.

    ``available=False`` adds an "unavailable" rule, ``True`` removes it.
    Returns how many toggles actually changed something.
    """
    changed = 0
    with transaction(conn):
        for resource_id, day, period, available in changes:
            if available:
                cur = conn.execute(
                    "DELETE FROM availability WHERE dataset_id = ? AND resource_id = ? AND day = ? AND period = ?",
                    (dataset_id, resource_id, day, period),
                )
            else:
                cur = conn.execute(
                    "INSERT OR IGNORE INTO availability VALUES (?, ?, ?, ?, 0)",
                    (dataset_id, resource_id, day, period),
                )
            changed += cur.rowcount
        _touch(conn, dataset_id)
    return changed


def update_fields(
    conn: sqlite3.Connection, table: str, key_column: str, dataset_id: int, ident: str, values: dict[str, object]
) -> bool:
    """Update columns of one row. ``table``/column names come from code, never from clients."""
    if not values:
        return False
    assignments = ", ".join(f"{col} = ?" for col in values)
    with transaction(conn):
        cur = conn.execute(
            f"UPDATE {table} SET {assignments} WHERE dataset_id = ? AND {key_column} = ?",  # noqa: S608
            (*values.values(), dataset_id, ident),
        )
        _touch(conn, dataset_id)
    return cur.rowcount > 0
