"""Turning uploaded bytes into the named files the importer needs.

Security rules applied here (nothing is ever written to disk):
  * file *names* are never trusted: only a sanitised base name is used and it
    is only compared with the eight known names;
  * every file is capped at ``MAX_FILE_BYTES``;
  * zip archives are read in memory with caps on member count, per-member and
    total uncompressed size; folder paths, ``..``, absolute paths, hidden and
    ``__MACOSX`` members are skipped with a warning;
  * non-CSV uploads are reported, not guessed at.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from typing import Optional

from .. import settings
from .report import ReportBuilder
from .schema import SPEC_BY_FILENAME, SPEC_BY_KEY

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


@dataclass
class IncomingFile:
    """One uploaded file after the web layer has read (at most MAX+1 bytes of) it."""

    filename: str  # as supplied by the client; untrusted
    data: Optional[bytes]  # None when it was too large to read
    field: str = ""  # multipart field name, used as a fallback identifier
    too_large: bool = False


def safe_name(filename: str) -> str:
    """Base name only, control characters removed, at most 80 characters."""
    base = filename.replace("\\", "/").rsplit("/", 1)[-1]
    return _CONTROL.sub("", base).strip()[:80] or "(unnamed)"


def _unsafe_path(name: str) -> bool:
    norm = name.replace("\\", "/")
    parts = [p for p in norm.split("/") if p]
    return norm.startswith("/") or ".." in parts or bool(re.match(r"^[A-Za-z]:", norm)) or "\x00" in name


def _too_large(rb: ReportBuilder, name: str) -> None:
    limit_mb = settings.MAX_FILE_BYTES // (1024 * 1024)
    rb.error(name, "FILE_TOO_LARGE", f"{name} is larger than the {limit_mb} MB limit and was not read.",
             "A timetable CSV should be far smaller than this. Remove unneeded rows or columns and upload it again.")


def _from_zip(incoming: IncomingFile, rb: ReportBuilder) -> list[IncomingFile]:
    zname = safe_name(incoming.filename)
    assert incoming.data is not None
    try:
        zf = zipfile.ZipFile(io.BytesIO(incoming.data))
    except zipfile.BadZipFile:
        rb.error(zname, "BAD_ZIP", f"{zname} is not a valid zip file.",
                 "Create the zip again (select the CSV files, right-click, Send to > Compressed folder) and upload it.")
        return []
    members = [i for i in zf.infolist() if not i.is_dir()]
    if len(members) > settings.MAX_ZIP_MEMBERS:
        rb.error(zname, "ZIP_TOO_MANY_FILES",
                 f"{zname} contains {len(members)} files; the limit is {settings.MAX_ZIP_MEMBERS}.",
                 "Zip only the eight CSV files (teachers, subjects, batches, rooms, requirements, days, periods, availability).")
        return []
    if sum(i.file_size for i in members) > settings.MAX_ZIP_TOTAL_BYTES:
        rb.error(zname, "ZIP_TOO_LARGE", f"{zname} would expand to more than {settings.MAX_ZIP_TOTAL_BYTES // (1024 * 1024)} MB.",
                 "Zip only the CSV files; they are normally a few kilobytes each.")
        return []
    out: list[IncomingFile] = []
    budget = settings.MAX_ZIP_TOTAL_BYTES
    for info in members:
        name = safe_name(info.filename)
        if _unsafe_path(info.filename):
            rb.warning(zname, "UNSAFE_ZIP_PATH", f"\"{name}\" inside {zname} was skipped because its path is not allowed.",
                       "Put the CSV files at the top level of the zip, without folders like ../")
            continue
        if info.filename.startswith("__MACOSX/") or name.startswith("."):
            continue  # OS metadata, silently irrelevant
        if info.flag_bits & 0x1:
            rb.error(name, "ZIP_ENCRYPTED", f"\"{name}\" inside {zname} is password protected and could not be read.",
                     "Create the zip again without a password.")
            continue
        try:
            with zf.open(info) as fh:
                data = fh.read(min(settings.MAX_FILE_BYTES, budget) + 1)
        except (zipfile.BadZipFile, RuntimeError, NotImplementedError, EOFError, OSError):
            rb.error(name, "BAD_ZIP", f"\"{name}\" inside {zname} could not be unpacked.",
                     "Create the zip again and upload it.")
            continue
        if len(data) > settings.MAX_FILE_BYTES:
            out.append(IncomingFile(filename=name, data=None, too_large=True))
            continue
        budget -= len(data)
        if budget < 0:
            rb.error(zname, "ZIP_TOO_LARGE", f"{zname} expands to more than the allowed size.",
                     "Zip only the CSV files.")
            return out
        out.append(IncomingFile(filename=name, data=data))
    return out


def resolve_files(uploads: list[IncomingFile], rb: ReportBuilder) -> dict[str, IncomingFile]:
    """Map the uploads to file keys (``teachers`` ...).  Problems go to ``rb``."""
    flat: list[IncomingFile] = []
    for up in uploads:
        name = safe_name(up.filename)
        if up.too_large or up.data is None:
            flat.append(IncomingFile(filename=name, data=None, field=up.field, too_large=True))
            continue
        # Only the ".zip" extension means "archive": .xlsx/.docx are zips internally but are not CSV.
        if name.lower().endswith(".zip"):
            flat.extend(_from_zip(up, rb))
        else:
            flat.append(IncomingFile(filename=name, data=up.data, field=up.field))

    found: dict[str, IncomingFile] = {}
    for item in flat:
        name = item.filename
        spec = SPEC_BY_FILENAME.get(name.lower())
        if spec is None and item.field:
            stem = item.field.lower().removesuffix(".csv")
            if stem in SPEC_BY_KEY and not name.lower().endswith((".xlsx", ".xls", ".pdf", ".zip")):
                spec = SPEC_BY_KEY[stem]
        if item.too_large:
            _too_large(rb, name)
            if spec is not None and spec.key not in found:
                found[spec.key] = IncomingFile(filename=spec.filename, data=None, too_large=True)
            continue
        if spec is None:
            if not name.lower().endswith(".csv"):
                rb.error(name, "NOT_CSV", f"{name} is not a CSV file, so it was not read.",
                         "Open it in Excel or Google Sheets, use File > Save As > CSV UTF-8, and upload the .csv file.")
            else:
                known = ", ".join(SPEC_BY_FILENAME)
                rb.warning(name, "UNKNOWN_FILE", f"{name} is not one of the files SmartSlot reads, so it was ignored.",
                           f"Rename it if it is meant to be one of: {known}.")
            continue
        if spec.key in found:
            rb.error(spec.filename, "DUPLICATE_FILE", f"{spec.filename} was supplied more than once.",
                     "Upload each file only once.")
            continue
        found[spec.key] = IncomingFile(filename=spec.filename, data=item.data, field=item.field)
    return found
