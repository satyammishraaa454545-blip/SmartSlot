"""Plain-English explanations for sessions the search could not place."""

from __future__ import annotations

from .candidates import Candidate, Problem, kind_label, room_kind
from .models import Entry, Session


def explain_unplaced(
    problem: Problem,
    session: Session,
    candidates: list[Candidate],
    placed: list[Entry],
    *,
    hit_limit: bool,
) -> tuple[list[str], list[str], list[str]]:
    """Return ``(reasons, reason_codes, hints)`` for a session left unscheduled
    by the search.

    ``candidates`` are the slots that were possible in principle (teacher free,
    suitable room free); we check which of them the ``placed`` classes took.
    """
    lk = problem.lk
    subj = lk.subject_name(session.subject_id)
    batch = lk.batch_name(session.batch_id)
    teacher = lk.teacher_name(session.teacher_id)
    label = f"{subj} for {batch}"

    taken: set[tuple[str, str, int]] = set()
    for e in placed:
        for p in e.periods:
            taken.add((e.teacher_id, e.day, p))
            taken.add((e.batch_id, e.day, p))
            taken.add((e.room_id, e.day, p))

    slots: dict[tuple[int, int], list[int]] = {}
    for di, start, ri in candidates:
        slots.setdefault((di, start), []).append(ri)

    by_teacher = by_batch = by_room = free = 0
    for (di, start), rooms in slots.items():
        day = problem.days[di]
        span = range(start, start + session.duration)
        if any((session.teacher_id, day, p) in taken for p in span):
            by_teacher += 1
        elif any((session.batch_id, day, p) in taken for p in span):
            by_batch += 1
        elif all(any((problem.rooms[ri].room_id, day, p) in taken for p in span) for ri in rooms):
            by_room += 1
        else:
            free += 1

    total = len(slots)
    kind = kind_label(room_kind(session))
    parts = []
    if by_teacher:
        parts.append(f"{by_teacher} clash with {teacher}'s other classes")
    if by_batch:
        parts.append(f"{by_batch} clash with {batch}'s other classes")
    if by_room:
        parts.append(f"{by_room} have no free {kind}")
    breakdown = ", ".join(parts[:-1]) + (" and " if len(parts) > 1 else "") + parts[-1] if parts else ""

    reasons: list[str] = []
    codes: list[str] = []
    hints: list[str] = []
    if hit_limit:
        reasons.append(
            f"{label}: the search stopped at its limit before a place was found for this session. "
            "A solution may still exist."
        )
        codes.append("SEARCH_LIMIT")
        hints.append("Run the generator again with a larger search limit.")
        detail = [f"{free} of its {total} possible slots were still open when the search stopped"] if free else []
        if breakdown:
            detail.append(f"of the rest, {breakdown}")
        if detail:
            reasons.append("In the best partial timetable found, " + "; ".join(detail) + ".")
        return reasons, codes, hints

    if total == 1:
        slots_phrase = "its only possible slot is"
    else:
        slots_phrase = f"all {total} possible slots are"
    reasons.append(
        f"{label}: {slots_phrase} already used by other classes in the best timetable found "
        f"(slots where {teacher} is free and a suitable {kind} exists)"
        + (f": {breakdown}." if breakdown else ".")
    )
    reasons.append(
        "The scheduler checked every possible arrangement and none places all sessions together, "
        "so this one is left out of the best timetable found."
    )
    codes.append("NO_FREE_SLOT")
    biggest = max((by_teacher, "teacher"), (by_batch, "batch"), (by_room, "room"))[1]
    if biggest == "teacher":
        hints.append(f"{teacher} is the bottleneck: reduce their weekly sessions, add availability, or reassign some classes.")
    elif biggest == "batch":
        hints.append(f"{batch} is over-booked: reduce its weekly sessions or add working periods.")
    else:
        hints.append(f"Add another {kind}, or move classes out of the busiest {kind}.")
    return reasons, codes, hints
