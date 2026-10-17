"""Independent timetable validator.

``validate(dataset, entries)`` recomputes every hard constraint straight from
the list of entries.  It deliberately shares NO placement logic with the
solver (no candidate generation, no occupancy masks): the solver is only
trusted because this module agrees with it.  The only shared code is the
read-only :class:`Lookup` and :func:`expand_sessions` (to know which sessions
are required).

Conflict codes are listed in ``models.CONFLICT_CODES``.  Output is sorted
deterministically (errors first, then day/period, code, entry ids).
"""

from __future__ import annotations

from typing import Optional
from collections.abc import Iterable

from .expand import expand_sessions
from .labels import day_name, period_phrase
from .lookup import Lookup
from .models import (
    CONFLICT_CODES,
    Conflict,
    Dataset,
    Entry,
    Involved,
    Session,
    Suggestion,
    ValidationReport,
)

# Only the first N conflicts get (relatively costly) alternative-slot suggestions.
MAX_CONFLICTS_WITH_SUGGESTIONS = 40
# Conflict codes for which moving the entry elsewhere can help.
_SUGGESTIBLE = {
    "TEACHER_OVERLAP",
    "ROOM_OVERLAP",
    "BATCH_OVERLAP",
    "TEACHER_UNAVAILABLE",
    "ROOM_UNAVAILABLE",
    "ROOM_CAPACITY",
    "ROOM_TYPE",
    "OUTSIDE_WORKING_HOURS",
    "BLOCKED_PERIOD",
    "MISSING_SESSION",
}


def _spans(periods: Iterable[int]) -> list[tuple[int, int]]:
    """Group sorted period numbers into (start, length) runs."""
    runs: list[tuple[int, int]] = []
    for p in sorted(set(periods)):
        if runs and runs[-1][0] + runs[-1][1] == p:
            runs[-1] = (runs[-1][0], runs[-1][1] + 1)
        else:
            runs.append((p, 1))
    return runs


def _phrase(periods: Iterable[int]) -> str:
    return " and ".join(period_phrase(s, n) for s, n in _spans(periods))


class _Validator:
    def __init__(self, dataset: Dataset, entries: list[Entry], focus: Optional[str]) -> None:
        self.ds = dataset
        self.entries = entries
        self.focus = focus
        self.lk = Lookup(dataset)
        self.sessions: dict[str, Session] = {s.session_id: s for s in expand_sessions(dataset)}
        self.conflicts: list[Conflict] = []

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _who(self, e: Entry) -> str:
        return f"{self.lk.batch_name(e.batch_id)} ({self.lk.subject_name(e.subject_id)})"

    def _add(
        self,
        code: str,
        message: str,
        entries: list[Entry],
        *,
        day: Optional[str] = None,
        period: Optional[int] = None,
        involved: Optional[Involved] = None,
        severity: str = "error",
        suggest_for: Optional[str] = None,
    ) -> None:
        ids = [e.session_id for e in entries]
        self.conflicts.append(
            Conflict(
                code=code,
                severity=severity,  # type: ignore[arg-type]
                message=message,
                day=day,
                period=period,
                entry_ids=ids,
                involved=involved or Involved(),
                suggested_entry_id=suggest_for if code in _SUGGESTIBLE else None,
            )
        )

    @staticmethod
    def _involved(e: Entry) -> Involved:
        return Involved(
            teacher_id=e.teacher_id, room_id=e.room_id, batch_id=e.batch_id, subject_id=e.subject_id
        )

    # ------------------------------------------------------------------
    # per-entry checks
    # ------------------------------------------------------------------
    def check_entry(self, e: Entry) -> None:
        lk = self.lk
        inv = self._involved(e)
        label = self._who(e)

        # --- references --------------------------------------------------
        for kind, ident, table in (
            ("teacher", e.teacher_id, lk.teachers),
            ("room", e.room_id, lk.rooms),
            ("subject", e.subject_id, lk.subjects),
            ("batch", e.batch_id, lk.batches),
        ):
            if ident not in table:
                self._add(
                    "INVALID_REFERENCE",
                    f"Class '{e.session_id}' refers to {kind} '{ident}', which does not exist in the data.",
                    [e],
                    day=e.day,
                    period=e.start_period,
                    involved=inv,
                )
        session = self.sessions.get(e.session_id)
        if session is None:
            self._add(
                "INVALID_REFERENCE",
                f"Class '{e.session_id}' does not match any required session "
                "(check the subject, batch and session number).",
                [e],
                day=e.day,
                period=e.start_period,
                involved=inv,
            )
        elif (session.subject_id, session.batch_id) != (e.subject_id, e.batch_id):
            self._add(
                "INVALID_REFERENCE",
                f"Class '{e.session_id}' is recorded for subject '{e.subject_id}' / batch "
                f"'{e.batch_id}' but belongs to subject '{session.subject_id}' / batch '{session.batch_id}'.",
                [e],
                day=e.day,
                period=e.start_period,
                involved=inv,
            )

        # --- duration ----------------------------------------------------
        if e.duration < 1:
            self._add(
                "INVALID_DURATION",
                f"{label} must last at least 1 period, but its duration is {e.duration}.",
                [e],
                day=e.day,
                period=e.start_period,
                involved=inv,
                suggest_for=e.session_id,
            )
        elif session is not None and e.duration != session.duration:
            self._add(
                "INVALID_DURATION",
                f"{label} needs {session.duration} consecutive period(s), "
                f"but it is scheduled for {e.duration}.",
                [e],
                day=e.day,
                period=e.start_period,
                involved=inv,
                suggest_for=e.session_id,
            )

        # --- working hours / breaks -------------------------------------------
        periods = list(e.periods)
        defined = lk.period_defs
        if e.day not in lk.day_index:
            self._add(
                "OUTSIDE_WORKING_HOURS",
                f"{day_name(e.day)} is not a working day (working days: "
                f"{', '.join(day_name(d) for d in lk.days)}).",
                [e],
                day=e.day,
                period=e.start_period,
                involved=inv,
                suggest_for=e.session_id,
            )
        if periods and defined:
            lo, hi = min(defined), max(defined)
            outside = [p for p in periods if p < lo or p > hi]
            if outside:
                self._add(
                    "OUTSIDE_WORKING_HOURS",
                    f"{label} is placed in {_phrase(outside)} on {day_name(e.day)}, which is outside "
                    f"the working day (periods {lo}-{hi}).",
                    [e],
                    day=e.day,
                    period=e.start_period,
                    involved=inv,
                    suggest_for=e.session_id,
                )
            breaks = [p for p in periods if p in defined and defined[p].is_break]
            holes = [p for p in periods if lo <= p <= hi and p not in defined]
            if breaks or holes:
                what = _phrase(breaks or holes)
                if len(periods) > 1:
                    msg = (
                        f"{label} cannot run across {what} on {day_name(e.day)} because it "
                        f"{'is a break' if breaks else 'is not a teaching period'}; "
                        "a multi-period class must use consecutive teaching periods."
                    )
                else:
                    msg = (
                        f"{label} cannot be held in {what} on {day_name(e.day)} because it "
                        f"{'is a break' if breaks else 'is not a teaching period'}."
                    )
                self._add(
                    "BLOCKED_PERIOD",
                    msg,
                    [e],
                    day=e.day,
                    period=min(breaks or holes),
                    involved=inv,
                    suggest_for=e.session_id,
                )
        elif periods and not defined:
            self._add(
                "OUTSIDE_WORKING_HOURS",
                "No periods are configured, so no class can be scheduled.",
                [e],
                day=e.day,
                period=e.start_period,
                involved=inv,
                suggest_for=e.session_id,
            )

        # --- availability ---------------------------------------------------------
        if e.teacher_id in lk.teachers:
            gone = [p for p in periods if lk.is_unavailable(e.teacher_id, e.day, p)]
            if gone:
                self._add(
                    "TEACHER_UNAVAILABLE",
                    f"{lk.teacher_name(e.teacher_id)} is not available during {_phrase(gone)} "
                    f"on {day_name(e.day)} ({label}).",
                    [e],
                    day=e.day,
                    period=min(gone),
                    involved=inv,
                    suggest_for=e.session_id,
                )
        if e.room_id in lk.rooms:
            gone = [p for p in periods if lk.is_unavailable(e.room_id, e.day, p)]
            if gone:
                self._add(
                    "ROOM_UNAVAILABLE",
                    f"{lk.room_name(e.room_id)} is not available during {_phrase(gone)} "
                    f"on {day_name(e.day)} ({label}).",
                    [e],
                    day=e.day,
                    period=min(gone),
                    involved=inv,
                    suggest_for=e.session_id,
                )

        # --- room capacity / type ----------------------------------------------------
        room = lk.rooms.get(e.room_id)
        batch = lk.batches.get(e.batch_id)
        subject = lk.subjects.get(e.subject_id)
        if room is not None and batch is not None and room.capacity < batch.student_count:
            self._add(
                "ROOM_CAPACITY",
                f"{room.name} seats {room.capacity} but {batch.name} has {batch.student_count} students.",
                [e],
                day=e.day,
                period=e.start_period,
                involved=inv,
                suggest_for=e.session_id,
            )
        if room is not None and subject is not None:
            if subject.session_type == "practical" and room.room_type != "lab":
                self._add(
                    "ROOM_TYPE",
                    f"{subject.name} is a practical and needs a laboratory, but {room.name} is a classroom.",
                    [e],
                    day=e.day,
                    period=e.start_period,
                    involved=inv,
                    suggest_for=e.session_id,
                )
            elif subject.session_type == "lecture" and room.room_type != "classroom":
                self._add(
                    "ROOM_TYPE",
                    f"{subject.name} is a lecture and must be held in a classroom, but {room.name} is a lab.",
                    [e],
                    day=e.day,
                    period=e.start_period,
                    involved=inv,
                    suggest_for=e.session_id,
                )

    # ------------------------------------------------------------------
    # overlaps (teacher / room / batch)
    # ------------------------------------------------------------------
    def check_overlaps(self) -> None:
        lk = self.lk
        specs = (
            ("TEACHER_OVERLAP", lambda e: e.teacher_id, lk.teachers),
            ("ROOM_OVERLAP", lambda e: e.room_id, lk.rooms),
            ("BATCH_OVERLAP", lambda e: e.batch_id, lk.batches),
        )
        for code, key_of, table in specs:
            # (resource, day, period) -> indexes of entries occupying that cell
            cells: dict[tuple[str, str, int], list[int]] = {}
            for i, e in enumerate(self.entries):
                res = key_of(e)
                if res not in table:
                    continue  # unknown resources are reported as INVALID_REFERENCE
                for p in e.periods:
                    cells.setdefault((res, e.day, p), []).append(i)
            # (i, j, resource, day) -> overlapping periods, for i < j
            pairs: dict[tuple[int, int, str, str], list[int]] = {}
            for (res, day, p), idxs in cells.items():
                if len(idxs) < 2:
                    continue
                for a in range(len(idxs)):
                    for b in range(a + 1, len(idxs)):
                        pairs.setdefault((idxs[a], idxs[b], res, day), []).append(p)
            for (i, j, res, day), ps in pairs.items():
                a, b = self.entries[i], self.entries[j]
                # canonical order: by session id so output does not depend on input order
                if (a.session_id, i) > (b.session_id, j):
                    a, b = b, a
                self._overlap_conflict(code, res, day, sorted(ps), a, b)

    def _overlap_conflict(
        self, code: str, res: str, day: str, ps: list[int], a: Entry, b: Entry
    ) -> None:
        lk = self.lk
        when = f"{_phrase(ps)} on {day_name(day)}"
        focus = self.focus
        # In focus mode the focused entry is "the new one"; the other is "already" there.
        existing, mover = (a, b) if focus == b.session_id else (b, a) if focus == a.session_id else (None, None)
        if code == "TEACHER_OVERLAP":
            name = lk.teacher_name(res)
            if existing is not None:
                msg = (
                    f"{name} is already assigned to {lk.batch_name(existing.batch_id)} during {when} "
                    f"({lk.subject_name(existing.subject_id)})."
                )
            else:
                msg = (
                    f"{name} is double-booked during {when}: teaching {self._who(a)} "
                    f"and {self._who(b)} at the same time."
                )
        elif code == "ROOM_OVERLAP":
            name = lk.room_name(res)
            if existing is not None:
                msg = (
                    f"{name} is already booked for {lk.batch_name(existing.batch_id)} "
                    f"({lk.subject_name(existing.subject_id)}) during {when}."
                )
            else:
                msg = f"{name} is double-booked during {when}: {self._who(a)} and {self._who(b)} are both scheduled there."
        else:
            name = lk.batch_name(res)
            if existing is not None:
                msg = (
                    f"{name} already has {lk.subject_name(existing.subject_id)} with "
                    f"{lk.teacher_name(existing.teacher_id)} during {when}."
                )
            else:
                msg = (
                    f"{name} has two classes at the same time during {when}: "
                    f"{lk.subject_name(a.subject_id)} and {lk.subject_name(b.subject_id)}."
                )
        if code == "TEACHER_OVERLAP":
            inv = Involved(teacher_id=res)
        elif code == "ROOM_OVERLAP":
            inv = Involved(room_id=res)
        else:
            inv = Involved(batch_id=res)
        suggest_for = mover.session_id if mover is not None else b.session_id
        self._add(code, msg, [a, b], day=day, period=ps[0], involved=inv, suggest_for=suggest_for)

    # ------------------------------------------------------------------
    # completeness
    # ------------------------------------------------------------------
    def check_missing(self) -> None:
        present = {e.session_id for e in self.entries}
        lk = self.lk
        for sid in sorted(self.sessions):
            if sid in present:
                continue
            s = self.sessions[sid]
            self.conflicts.append(
                Conflict(
                    code="MISSING_SESSION",
                    severity="warning",
                    message=(
                        f"{lk.subject_name(s.subject_id)} for {lk.batch_name(s.batch_id)} "
                        f"(session {s.index} of {s.of}, taught by {lk.teacher_name(s.teacher_id)}) "
                        "has not been scheduled."
                    ),
                    entry_ids=[sid],
                    involved=Involved(
                        teacher_id=s.teacher_id, batch_id=s.batch_id, subject_id=s.subject_id
                    ),
                    suggested_entry_id=sid,
                )
            )

    def check_duplicates(self) -> None:
        seen: dict[str, Entry] = {}
        for e in self.entries:
            if e.session_id in seen:
                self._add(
                    "INVALID_REFERENCE",
                    f"Class '{e.session_id}' appears more than once on the timetable; "
                    "each required session may be scheduled only once.",
                    [e],
                    day=e.day,
                    period=e.start_period,
                    involved=self._involved(e),
                )
            else:
                seen[e.session_id] = e

    # ------------------------------------------------------------------
    def run(self) -> list[Conflict]:
        self.check_duplicates()
        for e in self.entries:
            self.check_entry(e)
        self.check_overlaps()
        self.check_missing()
        self.conflicts.sort(key=self._sort_key)
        return self.conflicts

    def _sort_key(self, c: Conflict) -> tuple:
        day_key = self.lk.day_sort_key(c.day) if c.day is not None else (10_000, "")
        return (
            0 if c.severity == "error" else 1,
            day_key,
            c.period if c.period is not None else 10_000,
            CONFLICT_CODES.index(c.code),
            tuple(c.entry_ids),
            c.message,
        )


# Teacher-friendly names for the conflict codes, used in the one-line summary (the codes themselves stay stable).
CONFLICT_PHRASES: dict[str, str] = {
    "TEACHER_OVERLAP": "teacher double-booked",
    "ROOM_OVERLAP": "room double-booked",
    "BATCH_OVERLAP": "batch has two classes at once",
    "TEACHER_UNAVAILABLE": "teacher not available",
    "ROOM_UNAVAILABLE": "room not available",
    "ROOM_CAPACITY": "room too small",
    "ROOM_TYPE": "wrong type of room",
    "INVALID_DURATION": "invalid length",
    "OUTSIDE_WORKING_HOURS": "outside working hours",
    "BLOCKED_PERIOD": "placed in a break",
    "INVALID_REFERENCE": "unknown teacher, room or subject",
}


def _summary(error_count: int, warning_count: int, total_sessions: int, counts: dict[str, int]) -> str:
    if error_count:
        kinds = ", ".join(
            f"{CONFLICT_PHRASES.get(code, code.lower().replace('_', ' '))}: {n}"
            for code, n in sorted(counts.items())
            if code != "MISSING_SESSION"
        )
        noun = "conflict" if error_count == 1 else "conflicts"
        return f"{error_count} {noun} must be fixed before this timetable can be published ({kinds})."
    if warning_count:
        return (
            f"No conflicts, but {warning_count} of {total_sessions} required session(s) "
            "are not scheduled yet."
        )
    return f"Valid and complete: all {total_sessions} required sessions are scheduled with no conflicts."


def build_report(conflicts: list[Conflict], total_sessions: int) -> ValidationReport:
    errors = [c for c in conflicts if c.severity == "error"]
    missing = [c for c in conflicts if c.code == "MISSING_SESSION"]
    counts: dict[str, int] = {}
    for c in conflicts:
        counts[c.code] = counts.get(c.code, 0) + 1
    valid = not errors
    complete = valid and not missing
    return ValidationReport(
        valid=valid,
        complete=complete,
        status="valid_complete" if complete else ("valid_incomplete" if valid else "invalid"),
        error_count=len(errors),
        warning_count=len(conflicts) - len(errors),
        counts=counts,
        summary=_summary(len(errors), len(conflicts) - len(errors), total_sessions, counts),
        conflicts=conflicts,
    )


def validate(
    dataset: Dataset,
    entries: Iterable[Entry],
    *,
    with_suggestions: bool = True,
    max_suggestions: int = 3,
    focus_entry_id: Optional[str] = None,
) -> ValidationReport:
    """Check ``entries`` against every hard constraint of ``dataset``.

    Pure function: neither argument is modified.  ``focus_entry_id`` only
    changes the *wording* of overlap messages ("X is already assigned to ...")
    so edit dialogs read naturally; the set of conflicts is unaffected.
    """
    v = _Validator(dataset, list(entries), focus_entry_id)
    conflicts = v.run()
    if with_suggestions and max_suggestions > 0:
        _attach_suggestions(dataset, v.entries, conflicts, max_suggestions)
    return build_report(conflicts, len(v.sessions))


def _attach_suggestions(
    dataset: Dataset, entries: list[Entry], conflicts: list[Conflict], limit: int
) -> None:
    from .suggest import suggest_slots  # local import: suggest depends on validate

    cache: dict[str, list[Suggestion]] = {}
    for c in conflicts[:MAX_CONFLICTS_WITH_SUGGESTIONS]:
        target = c.suggested_entry_id
        if target is None:
            continue
        if target not in cache:
            cache[target] = suggest_slots(dataset, entries, target, limit=limit)
        c.suggestions = list(cache[target])
