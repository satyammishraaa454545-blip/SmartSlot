"""CSV export of a version's scheduled classes (one row per class)."""

from __future__ import annotations

import csv
import io

from ..schemas import EntryOut

COLUMNS = (
    "session_id", "batch_id", "batch_name", "subject_id", "subject_name", "session_type",
    "teacher_id", "teacher_name", "room_id", "room_name", "room_type",
    "day", "start_period", "end_period", "duration", "start_time", "end_time",
)
_TEXT = {"session_id", "batch_id", "batch_name", "subject_id", "subject_name", "teacher_id", "teacher_name",
         "room_id", "room_name"}
_FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")


def _safe(value: object, column: str) -> object:
    """Stop spreadsheet programs from running text such as ``=cmd|...`` (CSV injection)."""
    if column in _TEXT and isinstance(value, str) and value.startswith(_FORMULA_STARTS):
        return "'" + value
    return "" if value is None else value


def entries_to_csv(entries: list[EntryOut]) -> bytes:
    """UTF-8 with a BOM so Excel shows names correctly; rows are in timetable order."""
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow(COLUMNS)
    for e in entries:
        data = e.model_dump()
        data["session_type"] = e.subject_type
        writer.writerow([_safe(data.get(col), col) for col in COLUMNS])
    return buf.getvalue().encode("utf-8-sig")
