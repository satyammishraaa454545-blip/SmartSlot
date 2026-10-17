"""Diff two versions of the same dataset in plain English."""

from __future__ import annotations

import sqlite3

from ..engine.models import Entry
from ..errors import ApiError
from ..repo import versions as version_repo
from ..schemas import ChangeOut, CompareOut, CompareSummary, VersionRef
from .enrich import Enricher
from .state import load_dataset_for, load_version_row, status_label


def _short(e: Entry) -> str:
    """``Mon P1`` or ``Mon P5-6`` for a multi-period class."""
    end = e.start_period + e.duration - 1
    span = f"P{e.start_period}" if e.duration <= 1 else f"P{e.start_period}-{end}"
    return f"{e.day} {span}"


def _ref(row: sqlite3.Row) -> VersionRef:
    return VersionRef(id=row["id"], label=row["label"], status=row["status"],
                      status_label=status_label(row["status"], bool(row["is_complete"])))


def compare_versions(conn: sqlite3.Connection, from_id: int, to_id: int) -> CompareOut:
    a_row, b_row = load_version_row(conn, from_id), load_version_row(conn, to_id)
    if a_row["dataset_id"] != b_row["dataset_id"]:
        raise ApiError(422, "DIFFERENT_DATASETS",
                       "These two versions belong to different datasets and cannot be compared.")
    dataset = load_dataset_for(conn, a_row["dataset_id"])
    enricher = Enricher(dataset)
    lk = enricher.lk
    before = {e.session_id: e for e in version_repo.load_entries(conn, from_id)}
    after = {e.session_id: e for e in version_repo.load_entries(conn, to_id)}

    changes: list[tuple[int, str, ChangeOut]] = []
    counts = {"added": 0, "removed": 0, "moved": 0, "room_changed": 0, "teacher_changed": 0, "unchanged": 0}

    def make(kind: str, sid: str, a: Entry | None, b: Entry | None, text: str, aspects: list[str]) -> ChangeOut:
        ref = b or a
        assert ref is not None
        return ChangeOut(
            type=kind,  # type: ignore[arg-type]
            aspects=aspects,  # type: ignore[arg-type]
            session_id=sid, subject_id=ref.subject_id, subject_name=lk.subject_name(ref.subject_id),
            batch_id=ref.batch_id, batch_name=lk.batch_name(ref.batch_id), text=text,
            before=enricher.entry(a) if a else None, after=enricher.entry(b) if b else None,
        )

    for sid in sorted(set(before) | set(after)):
        a, b = before.get(sid), after.get(sid)
        if a is None and b is not None:
            counts["added"] += 1
            text = f"{b.subject_id} for {lk.batch_name(b.batch_id)} was added on {_short(b)} in {lk.room_name(b.room_id)}"
            changes.append((1, sid, make("added", sid, None, b, text, [])))
        elif b is None and a is not None:
            counts["removed"] += 1
            text = f"{a.subject_id} for {lk.batch_name(a.batch_id)} was removed (was {_short(a)} in {lk.room_name(a.room_id)})"
            changes.append((2, sid, make("removed", sid, a, None, text, [])))
        elif a is not None and b is not None:
            aspects: list[str] = []
            parts: list[str] = []
            who = f"{b.subject_id} for {lk.batch_name(b.batch_id)}"
            if (a.day, a.start_period, a.duration) != (b.day, b.start_period, b.duration):
                aspects.append("moved")
                parts.append(f"moved {_short(a)} → {_short(b)}")
            if a.room_id != b.room_id:
                aspects.append("room_changed")
                parts.append(f"changed room {lk.room_name(a.room_id)} → {lk.room_name(b.room_id)}")
            if a.teacher_id != b.teacher_id:
                aspects.append("teacher_changed")
                parts.append(f"changed teacher {lk.teacher_name(a.teacher_id)} → {lk.teacher_name(b.teacher_id)}")
            if not aspects:
                counts["unchanged"] += 1
                continue
            for aspect in aspects:
                counts[aspect] += 1
            kind = aspects[0] if len(aspects) == 1 else "changed"
            changes.append((0, sid, make(kind, sid, a, b, f"{who} {'; '.join(parts)}", aspects)))

    changes.sort(key=lambda item: (item[0], item[1]))
    ordered = [c for _rank, _sid, c in changes]
    return CompareOut(
        from_version=_ref(a_row), to_version=_ref(b_row),
        summary=CompareSummary(changed_total=len(ordered), **counts),
        changes=ordered,
    )
