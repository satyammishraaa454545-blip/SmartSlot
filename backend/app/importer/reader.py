"""Bytes -> rows.  Handles encoding, delimiter, header and file-level problems.

Every problem that makes a whole file unusable is reported once as a file-level
issue (``row=None``).  Rows themselves are validated later by ``entities``.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from typing import Optional

from .. import settings
from .report import ReportBuilder
from .schema import FileSpec

# Leading bytes of common non-CSV formats (xlsx/zip/docx, xls, pdf, png, jpeg, exe, gzip).
_BINARY_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"PK\x03\x04", "an Excel (.xlsx) or zip file"),
    (b"\xd0\xcf\x11\xe0", "an old Excel (.xls) file"),
    (b"%PDF", "a PDF"),
    (b"\x89PNG", "an image"),
    (b"\xff\xd8\xff", "an image"),
    (b"MZ", "a program"),
    (b"\x1f\x8b", "a compressed file"),
)


@dataclass
class RawRow:
    number: int  # spreadsheet row (header = row 1)
    cells: dict[str, str]
    extra: list[str] = field(default_factory=list)  # non-empty cells beyond the header width


@dataclass
class ParsedFile:
    spec: FileSpec
    columns: list[str]
    rows: list[RawRow]


def normalize_header(name: str) -> str:
    return re.sub(r"[\s\-]+", "_", name.strip().lower())


def clean_cell(value: str) -> str:
    """Trim and collapse inner whitespace (also line breaks inside quoted cells)."""
    return " ".join(value.split())


def _short(text: str, limit: int = 80) -> str:
    text = text.replace("\r", " ").replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1] + "..."


def parse_csv(spec: FileSpec, data: bytes, rb: ReportBuilder) -> Optional[ParsedFile]:
    """Parse ``data`` as ``spec``.  Returns ``None`` when the file is unusable
    (the reason has been added to ``rb``)."""
    name = spec.filename
    summary = rb.summaries[name]
    summary.present = True

    def fail(code: str, message: str, fix: str, **kw: object) -> None:
        rb.error(name, code, message, fix, **kw)  # type: ignore[arg-type]

    if not data.strip(b"\xef\xbb\xbf \t\r\n"):
        if not spec.required:
            return ParsedFile(spec=spec, columns=[], rows=[])  # optional file left blank: nothing to import
        fail("EMPTY_FILE", f"{name} is empty.",
             f"Add a header row ({spec.header_line}) followed by your data rows. "
             "A blank template is available from the Templates download.")
        return None

    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        fail("BAD_ENCODING", f"{name} is saved as UTF-16 (\"Unicode text\"), which SmartSlot cannot read.",
             "Re-save it as \"CSV UTF-8 (Comma delimited)\" from Excel (File > Save As), then upload it again.")
        return None
    for signature, what in _BINARY_SIGNATURES:
        if data.startswith(signature):
            fail("NOT_CSV", f"{name} looks like {what}, not a plain-text CSV file.",
                 "Open it in Excel or Google Sheets and use File > Save As > CSV UTF-8, then upload the .csv file.")
            return None
    if b"\x00" in data:
        fail("NOT_CSV", f"{name} contains binary data and is not a plain-text CSV file.",
             "Open it in Excel or Google Sheets and use File > Save As > CSV UTF-8, then upload the .csv file.")
        return None
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        fail("BAD_ENCODING",
             f"{name} is not valid UTF-8 text (unreadable byte at position {exc.start}).",
             "Re-save the file as \"CSV UTF-8 (Comma delimited)\" from Excel (File > Save As), then upload it again.")
        return None

    first_line = next((ln for ln in text.splitlines() if ln.strip()), "")
    if "," not in first_line and (";" in first_line or "\t" in first_line):
        sep = "semicolons" if ";" in first_line else "tabs"
        fail("WRONG_DELIMITER", f"{name} separates columns with {sep}, but SmartSlot needs commas.",
             "Save the file as \"CSV UTF-8 (Comma delimited)\", or replace the separators with commas.")
        return None

    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    columns: list[str] = []
    rows: list[RawRow] = []
    header_seen = False
    row_no = 0
    try:
        for record in reader:
            row_no += 1
            if not header_seen:
                if not any(c.strip() for c in record):
                    continue  # blank lines before the header
                header_seen = True
                columns = [normalize_header(c) for c in record]
                continue
            if not any(c.strip() for c in record):
                continue  # blank line between rows: ignored
            if len(rows) >= settings.MAX_CSV_ROWS:
                fail("TOO_MANY_ROWS", f"{name} has more than {settings.MAX_CSV_ROWS} data rows.",
                     "Split the data or remove rows that are not needed for this timetable.", row=row_no)
                return None
            cells = {col: clean_cell(record[i]) if i < len(record) else "" for i, col in enumerate(columns) if col}
            extra = [clean_cell(c) for c in record[len(columns):] if c.strip()]
            rows.append(RawRow(number=row_no, cells=cells, extra=extra))
    except csv.Error as exc:
        fail("MALFORMED_CSV",
             f"{name} could not be read past row {row_no + 1}: {exc}. Rows after that point were not imported.",
             "Check that every opening double quote has a closing one, or save the file again as CSV UTF-8.",
             row=row_no + 1)
        return None

    if not header_seen:
        fail("EMPTY_FILE", f"{name} has no header row.",
             f"The first row must be the header: {spec.header_line}")
        return None

    duplicates = sorted({c for c in columns if c and columns.count(c) > 1})
    if duplicates:
        fail("DUPLICATE_COLUMN", f"{name} has the column {', '.join(duplicates)} more than once.",
             "Keep one column of each name.")
        return None
    present_required = [c for c in spec.required_columns if c in columns]
    if not present_required:
        fail("WRONG_HEADER",
             f"{name} does not start with the expected header row. Expected: {spec.header_line}. "
             f"Found: {_short(','.join(columns))}.",
             "Put the column names in the first row exactly as in the template, or check that this is the right file.",
             row=1)
        return None
    missing = [c for c in spec.required_columns if c not in columns]
    for col in missing:
        fail("MISSING_COLUMN", f"{name} has no \"{col}\" column.",
             f"Add a column named {col} to the header row. Expected header: {spec.header_line}",
             row=1, field=col)
    if missing:
        return None
    for col in columns:
        if col and col not in spec.columns:
            rb.warning(name, "UNKNOWN_COLUMN", f"Column \"{col}\" in {name} is not used by SmartSlot and was ignored.",
                       f"Remove it, or rename it if it is a misspelled column. Known columns: {spec.header_line}",
                       row=1, field=col)

    summary.rows = len(rows)
    if not rows and spec.required:
        fail("EMPTY_FILE", f"{name} has a header but no data rows.",
             "Add at least one row, or upload a different file.")
    return ParsedFile(spec=spec, columns=columns, rows=rows)
