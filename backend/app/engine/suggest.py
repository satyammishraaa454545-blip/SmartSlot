"""Alternative-slot suggestions and dry-run edit validation.

* :func:`suggest_slots` lists (day, start_period, room) placements for one
  class that would pass the validator given every *other* entry.
* :func:`validate_move` / :func:`validate_place` back the edit API: they report
  whether a proposed change is allowed, why not, which classes it clashes with,
  and what could be done instead - without touching their inputs.

Candidate slots are pre-filtered with cheap set lookups, but every suggestion
that is returned has been confirmed by the real validator, so a suggestion can
never be one the validator would reject.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Union
from collections.abc import Iterable

from .expand import expand_sessions
from .lookup import Lookup
from .models import (
    Conflict,
    Dataset,
    Entry,
    Involved,
    MoveResult,
    Session,
    Suggestion,
)
from .validator import validate


class UnknownEntryError(ValueError):
    """The entry id is not on the timetable."""


class UnknownSessionError(ValueError):
    """The session id does not come from any requirement."""


Target = Union[Entry, Session, str]


@dataclass(frozen=True)
class _Spec:
    """What we need to know to place one class."""

    session_id: str
    subject_id: str
    batch_id: str
    teacher_id: str
    duration: int
    current: Optional[Entry]  # where it sits now (None if unscheduled)


def _resolve(dataset: Dataset, entries: list[Entry], target: Target) -> _Spec:
    sessions = {s.session_id: s for s in expand_sessions(dataset)}
    if isinstance(target, Entry):
        sid = target.session_id
        current: Optional[Entry] = target
    elif isinstance(target, Session):
        sid = target.session_id
        current = next((e for e in entries if e.session_id == sid), None)
    else:
        sid = target
        current = next((e for e in entries if e.session_id == sid), None)
    session = sessions.get(sid)
    if session is None and current is None:
        raise UnknownSessionError(f"No such session or entry: {sid!r}")
    if session is not None:
        teacher = current.teacher_id if current is not None else session.teacher_id
        return _Spec(sid, session.subject_id, session.batch_id, teacher, session.duration, current)
    assert current is not None
    return _Spec(sid, current.subject_id, current.batch_id, current.teacher_id, current.duration, current)


def _candidate_starts(lk: Lookup, duration: int) -> list[int]:
    """Start periods where ``duration`` consecutive teaching periods exist."""
    out = []
    for start in lk.teaching_periods:
        if all(
            (p in lk.period_defs and not lk.period_defs[p].is_break)
            for p in range(start, start + duration)
        ):
            out.append(start)
    return out


def suggest_slots(
    dataset: Dataset,
    entries: Iterable[Entry],
    target: Target,
    limit: int = 5,
    *,
    teacher_id: Optional[str] = None,
) -> list[Suggestion]:
    """Return up to ``limit`` valid alternative placements for ``target``.

    ``target`` is an entry, a session, or a session id.  The class keeps its
    current teacher (or ``teacher_id`` if given) and may change day, start
    period and room.  A scheduled class's own current slot is not returned.
    Order is deterministic: nearest to the current slot first for scheduled
    classes, best-spread slots first for unscheduled ones.
    """
    entries = list(entries)
    spec = _resolve(dataset, entries, target)
    if limit <= 0:
        return []
    teacher = teacher_id or spec.teacher_id
    lk = Lookup(dataset)
    batch = lk.batches.get(spec.batch_id)
    subject = lk.subjects.get(spec.subject_id)
    if batch is None or teacher not in lk.teachers or spec.duration < 1:
        return []
    want_type = "lab" if (subject is not None and subject.session_type == "practical") else "classroom"

    others = [e for e in entries if e.session_id != spec.session_id]
    # Occupied (resource, day, period) cells of everything else.
    taken: set[tuple[str, str, int]] = set()
    day_load: dict[str, int] = {}  # periods the batch already has per day
    same_subject_days: dict[str, int] = {}
    for e in others:
        for p in e.periods:
            taken.add((e.teacher_id, e.day, p))
            taken.add((e.room_id, e.day, p))
            taken.add((e.batch_id, e.day, p))
        if e.batch_id == spec.batch_id:
            day_load[e.day] = day_load.get(e.day, 0) + e.duration
            if e.subject_id == spec.subject_id:
                same_subject_days[e.day] = same_subject_days.get(e.day, 0) + 1

    cur = spec.current
    rooms = [
        (i, r)
        for i, r in enumerate(dataset.rooms)
        if r.room_type == want_type and r.capacity >= batch.student_count
    ]
    starts = _candidate_starts(lk, spec.duration)
    last_teaching = lk.teaching_periods[-1] if lk.teaching_periods else 0

    ranked: list[tuple[tuple, str, int, str]] = []
    for day in lk.days:
        for start in starts:
            span = range(start, start + spec.duration)
            if any(lk.is_unavailable(teacher, day, p) for p in span):
                continue
            if any((teacher, day, p) in taken or (spec.batch_id, day, p) in taken for p in span):
                continue
            for ridx, room in rooms:
                if any(lk.is_unavailable(room.room_id, day, p) for p in span):
                    continue
                if any((room.room_id, day, p) in taken for p in span):
                    continue
                if cur is not None:
                    if (day, start, room.room_id) == (cur.day, cur.start_period, cur.room_id):
                        continue
                    key: tuple = (
                        room.room_id != cur.room_id,
                        day != cur.day,
                        abs(start - cur.start_period),
                        lk.day_index[day],
                        start,
                        ridx,
                    )
                else:
                    ends_last = start + spec.duration - 1 == last_teaching
                    key = (
                        same_subject_days.get(day, 0) * 10 + day_load.get(day, 0) * 2 + (3 if ends_last else 0),
                        lk.day_index[day],
                        start,
                        room.capacity,
                        ridx,
                    )
                ranked.append((key, day, start, room.room_id))
    ranked.sort()

    result: list[Suggestion] = []
    for _key, day, start, room_id in ranked:
        trial = Entry(
            session_id=spec.session_id,
            day=day,
            start_period=start,
            duration=spec.duration,
            teacher_id=teacher,
            room_id=room_id,
            subject_id=spec.subject_id,
            batch_id=spec.batch_id,
        )
        report = validate(dataset, others + [trial], with_suggestions=False)
        if any(c.severity == "error" and spec.session_id in c.entry_ids for c in report.conflicts):
            continue  # pre-filter was too optimistic; the validator has the last word
        result.append(Suggestion(day=day, start_period=start, room_id=room_id, teacher_id=teacher))
        if len(result) >= limit:
            break
    return result


# --------------------------------------------------------------------------
# Dry-run edits
# --------------------------------------------------------------------------
def _evaluate(
    dataset: Dataset,
    entries: list[Entry],
    proposed: Entry,
    original: Optional[Entry],
    suggestion_limit: int,
) -> MoveResult:
    """Validate ``proposed`` replacing/adding the entry with its session id."""
    sid = proposed.session_id
    others = [e for e in entries if e.session_id != sid]
    report = validate(dataset, others + [proposed], with_suggestions=False, focus_entry_id=sid)
    blocking = [c for c in report.conflicts if c.severity == "error" and sid in c.entry_ids]
    if not blocking:
        return MoveResult(
            valid=True,
            entry=proposed,
            message="No conflicts: this change is safe to save.",
        )
    clash_ids = sorted({i for c in blocking for i in c.entry_ids if i != sid})
    affected = [e for e in others if e.session_id in clash_ids]
    wanted = suggestion_limit + 1
    suggestions = suggest_slots(dataset, others + [proposed], proposed, limit=wanted)
    if original is not None:
        suggestions = [
            s
            for s in suggestions
            if (s.day, s.start_period, s.room_id) != (original.day, original.start_period, original.room_id)
        ]
    suggestions = suggestions[:suggestion_limit]
    for c in blocking:
        c.suggestions = list(suggestions)
        c.suggested_entry_id = sid
    extra = len(blocking) - 1
    message = blocking[0].message
    if extra:
        message += f" {extra} more issue{'s' if extra > 1 else ''} also block{'' if extra > 1 else 's'} this change."
    return MoveResult(
        valid=False,
        entry=proposed,
        conflicts=blocking,
        affected_entries=affected,
        suggestions=suggestions,
        message=message,
    )


def validate_move(
    dataset: Dataset,
    entries: Iterable[Entry],
    entry_id: str,
    new_day: Optional[str] = None,
    new_start: Optional[int] = None,
    new_room: Optional[str] = None,
    new_teacher: Optional[str] = None,
    *,
    suggestion_limit: int = 5,
) -> MoveResult:
    """Dry-run moving / re-roomming / re-assigning one scheduled class.

    ``None`` arguments keep the current value.  Nothing is mutated.  Only
    conflicts that involve the moved class block the change (pre-existing
    problems elsewhere on the timetable are not this edit's fault).
    """
    entries = list(entries)
    current = next((e for e in entries if e.session_id == entry_id), None)
    if current is None:
        raise UnknownEntryError(f"No scheduled class with id {entry_id!r}")
    proposed = Entry(
        session_id=current.session_id,
        day=new_day if new_day is not None else current.day,
        start_period=new_start if new_start is not None else current.start_period,
        duration=current.duration,
        teacher_id=new_teacher if new_teacher is not None else current.teacher_id,
        room_id=new_room if new_room is not None else current.room_id,
        subject_id=current.subject_id,
        batch_id=current.batch_id,
    )
    return _evaluate(dataset, entries, proposed, current, suggestion_limit)


def validate_place(
    dataset: Dataset,
    entries: Iterable[Entry],
    session_id: str,
    day: str,
    start_period: int,
    room_id: str,
    teacher_id: Optional[str] = None,
    *,
    suggestion_limit: int = 5,
) -> MoveResult:
    """Dry-run placing a currently unscheduled session."""
    entries = list(entries)
    session = next((s for s in expand_sessions(dataset) if s.session_id == session_id), None)
    if session is None:
        raise UnknownSessionError(f"No such session: {session_id!r}")
    lk = Lookup(dataset)
    if any(e.session_id == session_id for e in entries):
        conflict = Conflict(
            code="INVALID_REFERENCE",
            severity="error",
            message=(
                f"{lk.subject_name(session.subject_id)} for {lk.batch_name(session.batch_id)} "
                f"(session {session.index} of {session.of}) is already scheduled; move it instead of placing it."
            ),
            entry_ids=[session_id],
            involved=Involved(batch_id=session.batch_id, subject_id=session.subject_id),
        )
        return MoveResult(valid=False, conflicts=[conflict], message=conflict.message)
    proposed = Entry(
        session_id=session_id,
        day=day,
        start_period=start_period,
        duration=session.duration,
        teacher_id=teacher_id or session.teacher_id,
        room_id=room_id,
        subject_id=session.subject_id,
        batch_id=session.batch_id,
    )
    return _evaluate(dataset, entries, proposed, None, suggestion_limit)
