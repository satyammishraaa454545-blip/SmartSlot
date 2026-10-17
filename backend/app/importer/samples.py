"""The bundled sample datasets (``sample_data/<kind>/``).

They are read as ordinary uploads, so samples go through exactly the same
validation as a user's files.
"""

from __future__ import annotations

from typing import Optional

from .. import settings
from .intake import IncomingFile
from .schema import FILE_SPECS

SAMPLE_KINDS: dict[str, str] = {
    "feasible": "Demo - CE Semester 3 (complete timetable)",
    "infeasible": "Demo - CE Semester 3 (impossible lab requirement)",
    "invalid": "Demo - CE Semester 3 (CSV with errors)",
}
SAMPLE_SEMESTER = "3"


class SampleNotFoundError(FileNotFoundError):
    """The sample folder is missing on disk."""


def sample_uploads(kind: str) -> Optional[list[IncomingFile]]:
    """Files of one sample as uploads; ``None`` for an unknown ``kind``."""
    if kind not in SAMPLE_KINDS:  # whitelist: ``kind`` is never used to build a path otherwise
        return None
    folder = settings.sample_dir() / kind
    if not folder.is_dir():
        raise SampleNotFoundError(f"Sample folder not found: {folder}")
    uploads = []
    for spec in FILE_SPECS:
        path = folder / spec.filename
        if path.is_file():
            uploads.append(IncomingFile(filename=spec.filename, data=path.read_bytes(), field=spec.key))
    return uploads
