"""ImportReport: what was imported, what was rejected and why."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from .. import settings
from .schema import FILE_ORDER, FILE_SPECS

Severity = Literal["error", "warning"]


class ImportIssue(BaseModel):
    """One problem found while importing.  ``row`` is the spreadsheet row
    (header = row 1); it is ``None`` for whole-file problems."""

    severity: Severity
    file: Optional[str] = None
    row: Optional[int] = None
    field: Optional[str] = None
    value: Optional[str] = None
    code: str
    message: str
    how_to_fix: str


class FileSummary(BaseModel):
    file: str
    key: str
    required: bool
    present: bool  # a file with this name was supplied
    rows: int = 0  # non-blank data rows read
    accepted: int = 0
    rejected: int = 0
    errors: int = 0
    warnings: int = 0


class ImportReport(BaseModel):
    status: Literal["ok", "has_errors"]
    error_count: int
    warning_count: int
    total_sessions: int = 0  # weekly sessions the accepted requirements expand into
    counts: dict[str, int] = Field(default_factory=dict)  # accepted records per file key
    files: list[FileSummary] = Field(default_factory=list)
    issues: list[ImportIssue] = Field(default_factory=list)
    truncated: bool = False  # some issues were not stored (counts stay exact)


class ReportBuilder:
    """Collects issues in a deterministic order and keeps exact counters."""

    def __init__(self) -> None:
        self._issues: list[tuple[tuple, ImportIssue]] = []
        self._stored_per_file: dict[Optional[str], int] = {}
        self.summaries: dict[str, FileSummary] = {
            s.filename: FileSummary(file=s.filename, key=s.key, required=s.required, present=False)
            for s in FILE_SPECS
        }
        self.error_rows: dict[str, set[int]] = {}  # file -> rows that have at least one error
        self.error_count = 0
        self.warning_count = 0
        self.truncated = False
        self._seq = 0

    def add(
        self,
        severity: Severity,
        file: Optional[str],
        code: str,
        message: str,
        how_to_fix: str,
        *,
        row: Optional[int] = None,
        field: Optional[str] = None,
        value: Optional[str] = None,
    ) -> None:
        if value is not None and len(value) > 80:
            value = value[:79] + "…"
        if len(message) > 400:
            message = message[:399] + "…"
        if severity == "error":
            self.error_count += 1
        else:
            self.warning_count += 1
        summary = self.summaries.get(file) if file else None
        if summary is not None:
            if severity == "error":
                summary.errors += 1
                if row is not None and row > 1 and file is not None:
                    self.error_rows.setdefault(file, set()).add(row)
            else:
                summary.warnings += 1
        stored = self._stored_per_file.get(file, 0)
        if stored >= settings.MAX_ISSUES_PER_FILE:
            self.truncated = True
            return
        self._stored_per_file[file] = stored + 1
        self._seq += 1
        issue = ImportIssue(
            severity=severity, file=file, row=row, field=field, value=value,
            code=code, message=message, how_to_fix=how_to_fix,
        )
        # Order: general issues first, then by file order, file-level before rows,
        # row number, errors before warnings, then discovery order.
        file_rank = -1 if file is None else FILE_ORDER.get(file, len(FILE_ORDER))
        key = (file_rank, file or "", row if row is not None else 0, 0 if severity == "error" else 1, self._seq)
        self._issues.append((key, issue))

    def error(self, file: Optional[str], code: str, message: str, how_to_fix: str, **kw) -> None:
        self.add("error", file, code, message, how_to_fix, **kw)

    def warning(self, file: Optional[str], code: str, message: str, how_to_fix: str, **kw) -> None:
        self.add("warning", file, code, message, how_to_fix, **kw)

    def build(self, counts: dict[str, int], total_sessions: int) -> ImportReport:
        for filename, summary in self.summaries.items():
            summary.rejected = len(self.error_rows.get(filename, ()))
            summary.accepted = max(summary.rows - summary.rejected, 0)
        issues = [issue for _key, issue in sorted(self._issues, key=lambda kv: kv[0])]
        return ImportReport(
            status="has_errors" if self.error_count else "ok",
            error_count=self.error_count,
            warning_count=self.warning_count,
            total_sessions=total_sessions,
            counts=counts,
            files=[self.summaries[s.filename] for s in FILE_SPECS],
            issues=issues,
            truncated=self.truncated,
        )
