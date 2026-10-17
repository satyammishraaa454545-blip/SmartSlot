"""Minimal CSV loader for the documented sample-data template.

This is intentionally small: it turns a directory of well-formed CSVs into a
:class:`Dataset` and raises :class:`DatasetLoadError` (with file + row) on the
first malformed value.  The phase-2 importer adds full row-level validation,
duplicate/reference checks and friendly "how to fix" messages.

Files (see sample_data/README.md): teachers, subjects, batches, rooms,
requirements, days, periods (required) and availability (optional).
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Optional, TypeVar
from collections.abc import Callable

from .labels import normalize_day
from .models import (
    AvailabilityRule,
    Batch,
    Config,
    Dataset,
    PeriodDef,
    Requirement,
    Room,
    Subject,
    Teacher,
)

T = TypeVar("T")

_TRUE = {"1", "true", "yes", "y", "t"}
_FALSE = {"0", "false", "no", "n", "f"}


class DatasetLoadError(ValueError):
    """A CSV file is missing or contains a malformed value."""


def parse_bool(value: str) -> bool:
    v = value.strip().lower()
    if v in _TRUE:
        return True
    if v in _FALSE:
        return False
    raise ValueError(f"expected one of 1/0/true/false/yes/no, got {value!r}")


def _read(path: Path, builder: Callable[[dict[str, str]], T], required: bool = True) -> list[T]:
    if not path.exists():
        if required:
            raise DatasetLoadError(f"Missing required file: {path.name}")
        return []
    rows: list[T] = []
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        for line_no, raw in enumerate(reader, start=2):  # header is row 1
            row = {(k or "").strip(): (v or "").strip() for k, v in raw.items()}
            if not any(row.values()):
                continue  # blank line
            try:
                rows.append(builder(row))
            except (KeyError, ValueError) as exc:
                raise DatasetLoadError(f"{path.name}, row {line_no}: {exc}") from exc
    return rows


def _day(value: str) -> str:
    day = normalize_day(value)
    if day is None:
        raise ValueError(f"unknown day name {value!r} (use Mon, Tue, Wed, Thu, Fri, Sat, Sun)")
    return day


def load_dataset_from_dir(
    path: str | Path, name: Optional[str] = None, semester: Optional[str] = None
) -> Dataset:
    """Load ``<path>/*.csv`` into a Dataset (name defaults to the folder name)."""
    d = Path(path)
    if not d.is_dir():
        raise DatasetLoadError(f"Not a directory: {d}")

    teachers = _read(
        d / "teachers.csv",
        lambda r: Teacher(teacher_id=r["teacher_id"], name=r["name"], department_id=r.get("department_id", "")),
    )
    subjects = _read(
        d / "subjects.csv",
        lambda r: Subject(
            subject_id=r["subject_id"],
            name=r["name"],
            department_id=r.get("department_id", ""),
            session_type=r["session_type"].lower(),  # type: ignore[arg-type]
        ),
    )
    batches = _read(
        d / "batches.csv",
        lambda r: Batch(
            batch_id=r["batch_id"],
            name=r["name"],
            semester=r.get("semester", ""),
            student_count=int(r["student_count"]),
            department_id=r.get("department_id", ""),
        ),
    )
    rooms = _read(
        d / "rooms.csv",
        lambda r: Room(
            room_id=r["room_id"],
            name=r["name"],
            capacity=int(r["capacity"]),
            room_type=r["room_type"].lower(),  # type: ignore[arg-type]
        ),
    )
    requirements = _read(
        d / "requirements.csv",
        lambda r: Requirement(
            subject_id=r["subject_id"],
            batch_id=r["batch_id"],
            teacher_id=r["teacher_id"],
            sessions_per_week=int(r["sessions_per_week"]),
            duration=int(r.get("duration") or 1),
        ),
    )
    availability = _read(
        d / "availability.csv",
        lambda r: AvailabilityRule(
            resource_id=r["resource_id"],
            day=_day(r["day"]),
            period=int(r["period"]),
            available=parse_bool(r["available"]),
        ),
        required=False,
    )
    days = _read(d / "days.csv", lambda r: _day(r["day"]))
    periods = _read(
        d / "periods.csv",
        lambda r: PeriodDef(
            period=int(r["period"]),
            start=r["start"],
            end=r["end"],
            is_break=parse_bool(r.get("is_break") or "0"),
        ),
    )
    if not days:
        raise DatasetLoadError("days.csv has no rows")
    if not periods:
        raise DatasetLoadError("periods.csv has no rows")

    sem = semester if semester is not None else (batches[0].semester if batches else "")
    return Dataset(
        name=name if name is not None else d.name,
        semester=sem,
        teachers=teachers,
        subjects=subjects,
        batches=batches,
        rooms=rooms,
        availability=availability,
        requirements=requirements,
        config=Config(days=days, periods=sorted(periods, key=lambda p: p.period)),
    )
