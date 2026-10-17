"""Pick a Unicode TrueType font for PDFs when the system has one; else Helvetica."""

from __future__ import annotations

import os
from pathlib import Path

from reportlab.lib.fonts import addMapping
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

_CANDIDATES: tuple[tuple[str, str], ...] = (
    (r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\segoeuib.ttf"),
    (r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\arialbd.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"),
    ("/Library/Fonts/Arial.ttf", "/Library/Fonts/Arial Bold.ttf"),
    ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
)

_fonts: tuple[str, str] | None = None


def pdf_fonts() -> tuple[str, str]:
    """``(regular, bold)`` font names registered with ReportLab (cached)."""
    global _fonts
    if _fonts is not None:
        return _fonts
    override = os.environ.get("SMARTSLOT_PDF_FONT")  # optional: path to a regular .ttf
    candidates = list(_CANDIDATES)
    if override:
        candidates.insert(0, (override, override))
    for regular, bold in candidates:
        if Path(regular).is_file() and Path(bold).is_file():
            try:
                pdfmetrics.registerFont(TTFont("SmartSlot-Regular", regular))
                pdfmetrics.registerFont(TTFont("SmartSlot-Bold", bold))
                addMapping("SmartSlot-Regular", 0, 0, "SmartSlot-Regular")
                addMapping("SmartSlot-Regular", 1, 0, "SmartSlot-Bold")
                addMapping("SmartSlot-Regular", 0, 1, "SmartSlot-Regular")
                addMapping("SmartSlot-Regular", 1, 1, "SmartSlot-Bold")
                _fonts = ("SmartSlot-Regular", "SmartSlot-Bold")
                return _fonts
            except Exception:  # unreadable/odd font file: try the next one
                continue
    _fonts = ("Helvetica", "Helvetica-Bold")
    return _fonts
