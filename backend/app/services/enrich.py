"""Turn engine objects into UI-ready payloads (names, times, labels).

Read-only: this module never changes the dataset or any timetable.
"""

from __future__ import annotations

from typing import Optional

from ..engine.expand import expand_sessions
from ..engine.labels import day_name, period_phrase
from ..engine.lookup import Lookup
from ..engine.models import (
    Conflict,
    Dataset,
    Entry,
    MoveResult,
    ReviewItem,
    Session,
    Suggestion,
    ValidationReport,
)
from ..repo.versions import UnscheduledNote
from ..schemas import (
    ConflictOut,
    EntryOut,
    MoveResultOut,
    ReviewOut,
    SuggestionOut,
    UnscheduledOut,
    ValidationOut,
)

DEFAULT_NOTE = UnscheduledNote(
    session_id="",
    reasons=["This class has not been placed on the timetable yet."],
    reason_codes=["NOT_SCHEDULED"],
    hints=["Pick one of the suggested slots, or place it manually."],
)
MANUAL_NOTE_REASON = "Removed from the timetable by the coordinator."


class Enricher:
    def __init__(self, dataset: Dataset) -> None:
        self.dataset = dataset
        self.lk = Lookup(dataset)
        self.sessions: dict[str, Session] = {s.session_id: s for s in expand_sessions(dataset)}

    # -- time helpers -------------------------------------------------------
    def times(self, start: int, duration: int) -> tuple[Optional[str], Optional[str]]:
        first = self.lk.period_defs.get(start)
        last = self.lk.period_defs.get(start + max(duration, 1) - 1)
        return (first.start if first else None, last.end if last else None)

    def sort_key(self, e: Entry) -> tuple:
        return (*self.lk.day_sort_key(e.day), e.start_period, e.batch_id, e.session_id)

    # -- entries ----------------------------------------------------------------
    def entry(self, e: Entry, review: Optional[ReviewItem] = None) -> EntryOut:
        lk = self.lk
        start_time, end_time = self.times(e.start_period, e.duration)
        subject = lk.subjects.get(e.subject_id)
        room = lk.rooms.get(e.room_id)
        return EntryOut(
            entry_id=e.session_id,
            session_id=e.session_id,
            day=e.day,
            start_period=e.start_period,
            end_period=e.start_period + max(e.duration, 1) - 1,
            duration=e.duration,
            start_time=start_time,
            end_time=end_time,
            subject_id=e.subject_id,
            subject_name=lk.subject_name(e.subject_id),
            subject_type=subject.session_type if subject else "lecture",
            batch_id=e.batch_id,
            batch_name=lk.batch_name(e.batch_id),
            teacher_id=e.teacher_id,
            teacher_name=lk.teacher_name(e.teacher_id),
            room_id=e.room_id,
            room_name=lk.room_name(e.room_id),
            room_type=room.room_type if room else "",
            needs_review=review is not None,
            review_messages=list(review.messages) if review else [],
        )

    def entries(self, entries: list[Entry], review: Optional[dict[str, ReviewItem]] = None) -> list[EntryOut]:
        review = review or {}
        return [self.entry(e, review.get(e.session_id)) for e in sorted(entries, key=self.sort_key)]

    def entry_label(self, e: Entry) -> str:
        return (f"{self.lk.subject_name(e.subject_id)} for {self.lk.batch_name(e.batch_id)} "
                f"({e.day} {period_phrase(e.start_period, e.duration)})")

    # -- suggestions / conflicts --------------------------------------------------
    def suggestion(self, s: Suggestion, duration: int) -> SuggestionOut:
        start_time, end_time = self.times(s.start_period, duration)
        return SuggestionOut(
            day=s.day,
            start_period=s.start_period,
            end_period=s.start_period + max(duration, 1) - 1,
            duration=duration,
            start_time=start_time,
            end_time=end_time,
            room_id=s.room_id,
            room_name=self.lk.room_name(s.room_id),
            teacher_id=s.teacher_id,
            teacher_name=self.lk.teacher_name(s.teacher_id) if s.teacher_id else None,
            label=f"{day_name(s.day)} {period_phrase(s.start_period, duration)} in {self.lk.room_name(s.room_id)}",
        )

    def _duration_for(self, entry_id: Optional[str], fallback: int = 1) -> int:
        session = self.sessions.get(entry_id or "")
        return session.duration if session else fallback

    def conflict(self, c: Conflict) -> ConflictOut:
        duration = self._duration_for(c.suggested_entry_id)
        return ConflictOut(
            code=c.code,
            severity=c.severity,
            message=c.message,
            day=c.day,
            period=c.period,
            entry_ids=list(c.entry_ids),
            involved=c.involved,
            suggestions=[self.suggestion(s, duration) for s in c.suggestions],
            suggested_entry_id=c.suggested_entry_id,
        )

    def validation(self, report: ValidationReport) -> ValidationOut:
        return ValidationOut(
            valid=report.valid,
            complete=report.complete,
            status=report.status,
            error_count=report.error_count,
            warning_count=report.warning_count,
            counts=dict(sorted(report.counts.items())),
            summary=report.summary,
            conflicts=[self.conflict(c) for c in report.conflicts],
        )

    def move_result(self, result: MoveResult, session_id: str) -> MoveResultOut:
        duration = result.entry.duration if result.entry else self._duration_for(session_id)
        return MoveResultOut(
            valid=result.valid,
            message=result.message,
            entry=self.entry(result.entry) if result.entry else None,
            # the same alternatives are attached to every blocking conflict: send them once, at the top level
            conflicts=[self.conflict(c).model_copy(update={"suggestions": []}) for c in result.conflicts],
            affected_entries=[self.entry(e) for e in sorted(result.affected_entries, key=self.sort_key)],
            suggestions=[self.suggestion(s, duration) for s in result.suggestions],
        )

    # -- unscheduled ------------------------------------------------------------------
    def unscheduled(
        self, entries: list[Entry], notes: dict[str, UnscheduledNote]
    ) -> list[UnscheduledOut]:
        """Every required session that is not on the timetable, in requirement order."""
        placed = {e.session_id for e in entries}
        out: list[UnscheduledOut] = []
        for session in self.sessions.values():
            if session.session_id in placed:
                continue
            note = notes.get(session.session_id, DEFAULT_NOTE)
            subject = self.lk.subjects.get(session.subject_id)
            out.append(UnscheduledOut(
                session_id=session.session_id,
                subject_id=session.subject_id,
                subject_name=self.lk.subject_name(session.subject_id),
                subject_type=subject.session_type if subject else session.session_type,
                batch_id=session.batch_id,
                batch_name=self.lk.batch_name(session.batch_id),
                teacher_id=session.teacher_id,
                teacher_name=self.lk.teacher_name(session.teacher_id),
                duration=session.duration,
                index=session.index,
                of=session.of,
                reasons=list(note.reasons),
                reason_codes=list(note.reason_codes),
                hints=list(note.hints),
            ))
        return out

    # -- review ---------------------------------------------------------------------------
    def review(self, item: ReviewItem, by_id: dict[str, Entry]) -> ReviewOut:
        entry = by_id.get(item.entry_id)
        return ReviewOut(
            entry_id=item.entry_id,
            label=self.entry_label(entry) if entry else item.entry_id,
            codes=list(item.codes),
            messages=list(item.messages),
        )
