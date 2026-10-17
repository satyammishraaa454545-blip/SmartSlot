"""Blank header-only CSV templates (generated from the file specs)."""

from __future__ import annotations

import io
import zipfile
from typing import Optional

from .schema import FILE_SPECS, SPEC_BY_KEY


def template_names() -> list[str]:
    return [s.key for s in FILE_SPECS]


def template_csv(key: str) -> Optional[bytes]:
    """Header row only (``teachers`` -> ``teacher_id,name,department_id``)."""
    spec = SPEC_BY_KEY.get(key)
    if spec is None:
        return None
    return (spec.header_line + "\r\n").encode("utf-8")


def templates_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for spec in FILE_SPECS:
            zf.writestr(spec.filename, spec.header_line + "\r\n")
    return buf.getvalue()
