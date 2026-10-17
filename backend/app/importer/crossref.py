"""Whole-dataset checks that need several files at once.

These produce *warnings* (the data is importable) except for "no teaching
period at all", which makes a timetable impossible.  Checks that depend on a
file that could not be read are skipped so one problem is reported once.
"""

from __future__ import annotations

from ..engine.models import PeriodDef, Requirement
from .entities import Registry
from .report import ReportBuilder


def _minutes(hhmm: str) -> int:
    hour, minute = hhmm.split(":")
    return int(hour) * 60 + int(minute)


def longest_teaching_run(periods: list[PeriodDef]) -> int:
    """Longest run of consecutively numbered, non-break periods."""
    teaching = sorted(p.period for p in periods if not p.is_break)
    best = run = 0
    previous = None
    for number in teaching:
        run = run + 1 if previous is not None and number == previous + 1 else 1
        best = max(best, run)
        previous = number
    return best


def check_periods(rb: ReportBuilder, periods: list[PeriodDef]) -> None:
    f = "periods.csv"
    if not periods:
        return
    if all(p.is_break for p in periods):
        rb.error(f, "NO_TEACHING_PERIODS", "Every period in periods.csv is marked as a break, so nothing can be scheduled.",
                 "Set is_break to 0 for the periods where classes can run.")
    ordered = sorted(periods, key=lambda p: p.period)
    for prev, cur in zip(ordered, ordered[1:], strict=False):
        if cur.period != prev.period + 1:
            rb.warning(f, "PERIOD_GAP", f"Period numbers jump from {prev.period} to {cur.period}. "
                       "A class can never span the gap.",
                       "Number periods 1, 2, 3, ... without gaps (a lunch break is its own numbered row).")
        if _minutes(cur.start) < _minutes(prev.end):
            rb.warning(f, "PERIOD_OVERLAP",
                       f"Period {cur.period} ({cur.start}-{cur.end}) starts before Period {prev.period} "
                       f"({prev.start}-{prev.end}) ends.",
                       "Check the start and end times so that periods follow each other without overlapping.")


def check_unused_and_semester(
    rb: ReportBuilder, reg: Registry, requirements: list[Requirement], semester: str, batch_semesters: dict[str, str]
) -> None:
    """Entities nobody uses, requirements that cannot fit, mixed semesters."""
    if "requirements" in reg.usable:
        used_teachers = {r.teacher_id for r in requirements}
        used_subjects = {r.subject_id for r in requirements}
        used_batches = {r.batch_id for r in requirements}
        for tid, row in reg.rows.get("teachers", {}).items():
            if tid not in used_teachers:
                rb.warning("teachers.csv", "TEACHER_WITHOUT_REQUIREMENTS",
                           f"Teacher {tid} ({reg.teachers[tid]}) is not assigned to any requirement, so will have no classes.",
                           "Add a row to requirements.csv for this teacher, or ignore this if they are not teaching this semester.",
                           row=row, field="teacher_id", value=tid)
        for sid, row in reg.rows.get("subjects", {}).items():
            if sid not in used_subjects:
                rb.warning("subjects.csv", "SUBJECT_WITHOUT_REQUIREMENTS",
                           f"Subject {sid} is not used by any requirement, so it will not be scheduled.",
                           "Add a row to requirements.csv for this subject, or ignore this if it is not offered this semester.",
                           row=row, field="subject_id", value=sid)
        for bid, row in reg.rows.get("batches", {}).items():
            if bid not in used_batches:
                rb.warning("batches.csv", "BATCH_WITHOUT_REQUIREMENTS",
                           f"Batch {bid} has no requirements, so it will have an empty timetable.",
                           "Add the batch's subjects to requirements.csv.",
                           row=row, field="batch_id", value=bid)
    if semester:
        for bid, sem in batch_semesters.items():
            if sem and sem != semester:
                rb.warning("batches.csv", "SEMESTER_MISMATCH",
                           f"Batch {bid} is for semester {sem}, but this dataset is for semester {semester}.",
                           "Make sure only batches of the same semester are mixed in one dataset.",
                           row=reg.rows.get("batches", {}).get(bid), field="semester", value=sem)


def check_durations(rb: ReportBuilder, reg: Registry, requirements: list[Requirement], periods: list[PeriodDef]) -> None:
    if "periods" not in reg.usable or not any(not p.is_break for p in periods):
        return
    longest = longest_teaching_run(periods)
    for req in requirements:
        if req.duration > longest:
            rb.warning("requirements.csv", "DURATION_TOO_LONG",
                       f"{req.subject_id} for {req.batch_id} needs {req.duration} consecutive periods, but the longest "
                       f"stretch of teaching periods without a break is {longest}. These sessions cannot be scheduled.",
                       "Reduce the duration, or change periods.csv so there is a long enough stretch without a break.",
                       row=reg.requirement_rows.get((req.subject_id, req.batch_id, req.teacher_id)),
                       field="duration", value=str(req.duration))
