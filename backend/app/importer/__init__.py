"""CSV import with row-level validation (Phase 2).

    from app.importer import import_files, IncomingFile

``import_files`` never raises on bad data; it returns a :class:`Dataset` of the
valid rows plus an :class:`ImportReport` listing every problem with its file,
spreadsheet row, field, value and how to fix it.
"""

from .intake import IncomingFile
from .pipeline import ImportResult, import_files
from .report import FileSummary, ImportIssue, ImportReport
from .samples import SAMPLE_KINDS, SAMPLE_SEMESTER, SampleNotFoundError, sample_uploads
from .schema import FILE_SPECS, FileSpec
from .templates import template_csv, template_names, templates_zip

__all__ = [
    "FILE_SPECS",
    "SAMPLE_KINDS",
    "SAMPLE_SEMESTER",
    "FileSpec",
    "FileSummary",
    "ImportIssue",
    "ImportReport",
    "ImportResult",
    "IncomingFile",
    "SampleNotFoundError",
    "import_files",
    "sample_uploads",
    "template_csv",
    "template_names",
    "templates_zip",
]
