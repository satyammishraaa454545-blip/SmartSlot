"""Expand weekly requirements into individual sessions."""

from __future__ import annotations

from .models import Dataset, Session


def expand_sessions(dataset: Dataset) -> list[Session]:
    """Turn each requirement into ``sessions_per_week`` sessions.

    Session ids look like ``CS101-CE-A-1`` (``<subject>-<batch>-<n>``).  The
    counter runs per (subject, batch) pair, so two requirements for the same
    pair (e.g. two teachers sharing a subject) still get unique ids.  The
    teacher is fixed by the requirement; the engine chooses day/period/room.
    Order follows ``dataset.requirements`` and is therefore deterministic.
    """
    subject_types = {s.subject_id: s.session_type for s in dataset.subjects}
    counters: dict[tuple[str, str], int] = {}
    sessions: list[Session] = []
    for req_index, req in enumerate(dataset.requirements):
        key = (req.subject_id, req.batch_id)
        stype = subject_types.get(req.subject_id, "lecture")
        for _ in range(req.sessions_per_week):
            counters[key] = counters.get(key, 0) + 1
            n = counters[key]
            sessions.append(
                Session(
                    session_id=f"{req.subject_id}-{req.batch_id}-{n}",
                    subject_id=req.subject_id,
                    batch_id=req.batch_id,
                    teacher_id=req.teacher_id,
                    duration=req.duration,
                    session_type=stype,
                    index=n,
                    of=req.sessions_per_week,
                    requirement_index=req_index,
                )
            )
    return sessions
