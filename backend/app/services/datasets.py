"""Datasets: import, summaries/detail, configuration and availability edits."""

from __future__ import annotations

import sqlite3
from typing import Any, Optional

from ..engine.labels import normalize_day
from ..engine.models import AvailabilityRule, Config, Dataset, PeriodDef
from ..errors import ApiError, not_found
from ..importer import IncomingFile, import_files
from ..importer.fields import parse_time
from ..repo import datasets as repo
from ..repo import versions as version_repo
from ..requests import AvailabilityBulk, AvailabilityPut, BatchPatch, ConfigIn, RoomPatch, RuleIn, TeacherPatch
from ..schemas import DatasetDetail, DatasetEditResponse, DatasetSummary, ImportResponse

_COUNT_TABLES = ("teachers", "subjects", "batches", "rooms", "requirements", "days", "periods", "availability")


def _counts(conn: sqlite3.Connection, dataset_id: int) -> dict[str, int]:
    out = {}
    for table in _COUNT_TABLES:  # fixed names, never user input
        out[table] = int(conn.execute(
            f"SELECT COUNT(*) AS n FROM {table} WHERE dataset_id = ?", (dataset_id,)  # noqa: S608
        ).fetchone()["n"])
    return out


def summary_of(conn: sqlite3.Connection, row: sqlite3.Row) -> DatasetSummary:
    report = repo.report_of(row)
    did = row["id"]
    published = version_repo.published_row(conn, did)
    total = conn.execute(
        "SELECT COALESCE(SUM(sessions_per_week), 0) AS n FROM requirements WHERE dataset_id = ?", (did,)
    ).fetchone()["n"]
    return DatasetSummary(
        id=did, name=row["name"], semester=row["semester"], source=row["source"],
        import_status=row["import_status"], created_at=row["created_at"], updated_at=row["updated_at"],
        counts=_counts(conn, did), error_count=report.error_count, warning_count=report.warning_count,
        total_sessions=int(total), version_count=version_repo.version_count(conn, did),
        published_version_id=published["id"] if published else None,
    )


def get_row_or_404(conn: sqlite3.Connection, dataset_id: int) -> sqlite3.Row:
    row = repo.get_row(conn, dataset_id)
    if row is None:
        raise not_found("dataset", dataset_id)
    return row


def list_summaries(conn: sqlite3.Connection) -> list[DatasetSummary]:
    return [summary_of(conn, row) for row in repo.list_rows(conn)]


def detail_of(conn: sqlite3.Connection, dataset_id: int) -> DatasetDetail:
    row = get_row_or_404(conn, dataset_id)
    dataset = repo.load_dataset(conn, dataset_id)
    summary = summary_of(conn, row)
    return DatasetDetail(
        **summary.model_dump(),
        import_report=repo.report_of(row),
        teachers=dataset.teachers, subjects=dataset.subjects, batches=dataset.batches, rooms=dataset.rooms,
        requirements=dataset.requirements, days=dataset.config.days, periods=dataset.config.periods,
        teaching_periods=sorted(p.period for p in dataset.config.periods if not p.is_break),
        availability=dataset.availability,
    )


# ---------------------------------------------------------------------------
# import
# ---------------------------------------------------------------------------
def import_dataset(
    conn: sqlite3.Connection, uploads: list[IncomingFile], *, name: str, semester: str, source: str = "upload"
) -> ImportResponse:
    """Validate the files and store the result.  A dataset with errors is stored too
    (so the report can be shown), flagged ``has_errors``; generation is blocked for it."""
    result = import_files(uploads, name=name, semester=semester)
    dataset_id = repo.insert_dataset(
        conn, name=name, semester=result.dataset.semester, source=source,
        dataset=result.dataset, report=result.report,
    )
    summary = summary_of(conn, get_row_or_404(conn, dataset_id))
    return ImportResponse(dataset=summary, import_report=result.report, can_generate=result.report.status == "ok")


def delete_dataset(conn: sqlite3.Connection, dataset_id: int, *, force: bool) -> None:
    row = get_row_or_404(conn, dataset_id)
    published = version_repo.published_row(conn, dataset_id)
    if published is not None and not force:
        raise ApiError(
            409, "DATASET_HAS_PUBLISHED_VERSION",
            f"'{row['name']}' has a published timetable ({published['label']}). Deleting the dataset would delete "
            "it too. Send ?force=true to delete everything.",
            published_version_id=published["id"],
        )
    repo.delete_dataset(conn, dataset_id)


# ---------------------------------------------------------------------------
# configuration
# ---------------------------------------------------------------------------
def _config_problems(body: ConfigIn) -> tuple[Optional[Config], list[dict[str, Any]]]:
    problems: list[dict[str, Any]] = []
    days: list[str] = []
    for i, raw in enumerate(body.days):
        day = normalize_day(raw)
        if day is None:
            problems.append({"field": f"days[{i}]", "value": raw, "message": f"'{raw}' is not a valid day. Use Mon, Tue, Wed, Thu, Fri, Sat or Sun."})
        elif day in days:
            problems.append({"field": f"days[{i}]", "value": raw, "message": f"{day} is listed more than once."})
        else:
            days.append(day)
    periods: list[PeriodDef] = []
    seen: set[int] = set()
    for i, p in enumerate(body.periods):
        start, end = parse_time(p.start), parse_time(p.end)
        if start is None:
            problems.append({"field": f"periods[{i}].start", "value": p.start, "message": f"'{p.start}' is not a valid 24-hour time (HH:MM)."})
        if end is None:
            problems.append({"field": f"periods[{i}].end", "value": p.end, "message": f"'{p.end}' is not a valid 24-hour time (HH:MM)."})
        if start and end and end <= start:
            problems.append({"field": f"periods[{i}].end", "value": p.end, "message": f"Period {p.period} must end after it starts ({start})."})
        if p.period in seen:
            problems.append({"field": f"periods[{i}].period", "value": p.period, "message": f"Period {p.period} is defined more than once."})
        seen.add(p.period)
        if start and end:
            periods.append(PeriodDef(period=p.period, start=start, end=end, is_break=p.is_break))
    if all(p.is_break for p in body.periods):
        problems.append({"field": "periods", "value": None, "message": "At least one period must be a teaching period (is_break = false)."})
    if problems:
        return None, problems
    return Config(days=days, periods=sorted(periods, key=lambda p: p.period)), []


def update_config(conn: sqlite3.Connection, dataset_id: int, body: ConfigIn) -> DatasetEditResponse:
    get_row_or_404(conn, dataset_id)
    config, problems = _config_problems(body)
    if config is None:
        raise ApiError(422, "INVALID_CONFIG", "The days/periods were not saved: " + problems[0]["message"], errors=problems)
    before = repo.load_dataset(conn, dataset_id)
    repo.replace_config(conn, dataset_id, config)
    warnings: list[str] = []
    gone_days = set(before.config.days) - set(config.days)
    gone_periods = {p.period for p in before.config.periods} - {p.period for p in config.periods}
    stale = sum(1 for r in before.availability if r.day in gone_days or r.period in gone_periods)
    if stale:
        warnings.append(f"{stale} availability rule(s) refer to days or periods that no longer exist; they have no effect.")
    if version_repo.version_count(conn, dataset_id):
        warnings.append("Existing timetable versions were made with the old days/periods. Open them and check "
                        "their validation, or generate a new version.")
    return DatasetEditResponse(dataset=detail_of(conn, dataset_id), warnings=warnings)


# ---------------------------------------------------------------------------
# availability
# ---------------------------------------------------------------------------
def _check_rules(dataset: Dataset, rules: list[RuleIn]) -> tuple[list[tuple[str, str, int, bool]], list[dict[str, Any]], list[str]]:
    resources = {t.teacher_id for t in dataset.teachers} | {r.room_id for r in dataset.rooms}
    periods = {p.period: p for p in dataset.config.periods}
    clean: list[tuple[str, str, int, bool]] = []
    problems: list[dict[str, Any]] = []
    warnings: list[str] = []
    for i, rule in enumerate(rules):
        day = normalize_day(rule.day)
        ok = True
        if rule.resource_id not in resources:
            problems.append({"index": i, "field": "resource_id", "value": rule.resource_id,
                             "message": f"'{rule.resource_id}' is not a teacher id or room id in this dataset."})
            ok = False
        if day is None or day not in dataset.config.days:
            problems.append({"index": i, "field": "day", "value": rule.day,
                             "message": f"'{rule.day}' is not one of the working days ({', '.join(dataset.config.days)})."})
            ok = False
        if rule.period not in periods:
            problems.append({"index": i, "field": "period", "value": rule.period,
                             "message": f"Period {rule.period} is not defined for this dataset."})
            ok = False
        elif periods[rule.period].is_break:
            warnings.append(f"Period {rule.period} is a break; a rule on it has no effect.")
        if ok and day is not None:
            clean.append((rule.resource_id, day, rule.period, rule.available))
    return clean, problems, sorted(set(warnings))


def _reject_rules(problems: list[dict[str, Any]]) -> ApiError:
    return ApiError(422, "INVALID_AVAILABILITY",
                    f"Availability was not saved: {problems[0]['message']}" + (f" (and {len(problems) - 1} more)" if len(problems) > 1 else ""),
                    errors=problems)


def replace_availability(conn: sqlite3.Connection, dataset_id: int, body: AvailabilityPut) -> DatasetEditResponse:
    get_row_or_404(conn, dataset_id)
    dataset = repo.load_dataset(conn, dataset_id)
    clean, problems, warnings = _check_rules(dataset, body.rules)
    if problems:
        raise _reject_rules(problems)
    rules = [AvailabilityRule(resource_id=r, day=d, period=p, available=False) for r, d, p, avail in clean if not avail]
    repo.replace_availability(conn, dataset_id, rules)
    return DatasetEditResponse(dataset=detail_of(conn, dataset_id), warnings=warnings)


def toggle_availability(conn: sqlite3.Connection, dataset_id: int, changes: list[RuleIn]) -> DatasetEditResponse:
    get_row_or_404(conn, dataset_id)
    dataset = repo.load_dataset(conn, dataset_id)
    clean, problems, warnings = _check_rules(dataset, changes)
    if problems:
        raise _reject_rules(problems)
    repo.set_unavailable(conn, dataset_id, clean)
    return DatasetEditResponse(dataset=detail_of(conn, dataset_id), warnings=warnings)


def bulk_availability(conn: sqlite3.Connection, dataset_id: int, body: AvailabilityBulk) -> DatasetEditResponse:
    return toggle_availability(conn, dataset_id, body.changes)


# ---------------------------------------------------------------------------
# light editing of rooms / teachers / batches
# ---------------------------------------------------------------------------
def patch_entity(
    conn: sqlite3.Connection, dataset_id: int, table: str, key_column: str, ident: str,
    body: RoomPatch | TeacherPatch | BatchPatch, kind: str,
) -> DatasetEditResponse:
    get_row_or_404(conn, dataset_id)
    values = body.model_dump(exclude_none=True)
    if not values:
        raise ApiError(422, "NOTHING_TO_CHANGE", f"Send at least one field to change on the {kind}.")
    if not repo.update_fields(conn, table, key_column, dataset_id, ident, values):
        raise ApiError(404, f"{kind.upper()}_NOT_FOUND", f"This dataset has no {kind} with id '{ident}'.")
    warnings = []
    if version_repo.version_count(conn, dataset_id):
        warnings.append(f"The {kind} was updated. Existing timetable versions are re-checked automatically; "
                        "open them to see anything that now needs review.")
    return DatasetEditResponse(dataset=detail_of(conn, dataset_id), warnings=warnings)
