"""The importer entry point: uploaded files -> validated Dataset + ImportReport."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..engine.expand import expand_sessions
from ..engine.models import AvailabilityRule, Config, Dataset, PeriodDef, Requirement
from . import crossref, entities
from .entities import Registry
from .intake import IncomingFile, resolve_files
from .reader import ParsedFile, parse_csv
from .report import ImportReport, ReportBuilder
from .schema import FILE_SPECS


@dataclass
class ImportResult:
    """``dataset`` holds only the rows that passed validation."""

    dataset: Dataset
    report: ImportReport


def import_files(uploads: list[IncomingFile], name: str, semester: str = "") -> ImportResult:
    """Validate every uploaded file and build the dataset from the valid rows.

    Never raises for bad data: all problems end up in ``report.issues`` and
    ``report.status`` becomes ``has_errors``.
    """
    rb = ReportBuilder()
    files = resolve_files(uploads, rb)
    dataset = _build(rb, files, name, semester)
    counts = {
        "teachers": len(dataset.teachers),
        "subjects": len(dataset.subjects),
        "batches": len(dataset.batches),
        "rooms": len(dataset.rooms),
        "requirements": len(dataset.requirements),
        "days": len(dataset.config.days),
        "periods": len(dataset.config.periods),
        "availability": len(dataset.availability),
    }
    report = rb.build(counts, total_sessions=len(expand_sessions(dataset)))
    return ImportResult(dataset=dataset, report=report)


def _build(rb: ReportBuilder, files: dict[str, IncomingFile], name: str, semester: str) -> Dataset:
    reg = Registry()
    parsed: dict[str, Optional[ParsedFile]] = {}
    for spec in FILE_SPECS:
        incoming = files.get(spec.key)
        if incoming is None:
            parsed[spec.key] = None
            if spec.required:
                rb.error(spec.filename, "MISSING_FILE", f"{spec.filename} was not provided.",
                         f"Upload {spec.filename}. Its header row must be: {spec.header_line}")
            continue
        if incoming.data is None:  # supplied but unreadable (too large): already reported by the intake
            rb.summaries[spec.filename].present = True
            parsed[spec.key] = None
            continue
        parsed[spec.key] = parse_csv(spec, incoming.data, rb)

    def load(key: str, loader):  # type: ignore[no-untyped-def]
        """Run ``loader`` on a readable file and mark the file usable for references."""
        pf = parsed.get(key)
        if pf is None:
            return []
        result = loader(rb, pf, reg)
        if pf.rows:
            reg.usable.add(key)
        return result

    teachers = load("teachers", entities.load_teachers)
    subjects = load("subjects", entities.load_subjects)
    batches = load("batches", entities.load_batches)
    rooms = load("rooms", entities.load_rooms)
    requirements: list[Requirement] = load("requirements", entities.load_requirements)
    days: list[str] = load("days", entities.load_days)
    periods: list[PeriodDef] = load("periods", entities.load_periods)
    availability: list[AvailabilityRule] = load("availability", entities.load_availability)

    crossref.check_periods(rb, periods)
    crossref.check_durations(rb, reg, requirements, periods)
    batch_semesters = {b.batch_id: b.semester for b in batches}
    semester = semester.strip() or next((b.semester for b in batches if b.semester), "")
    crossref.check_unused_and_semester(rb, reg, requirements, semester, batch_semesters)

    return Dataset(
        name=name,
        semester=semester,
        teachers=teachers,
        subjects=subjects,
        batches=batches,
        rooms=rooms,
        availability=availability,
        requirements=requirements,
        config=Config(days=days, periods=periods),
    )
