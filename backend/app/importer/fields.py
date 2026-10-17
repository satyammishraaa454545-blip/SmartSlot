"""Cell-level parsing and validation helpers used by every file validator."""

from __future__ import annotations

import re
from typing import Optional

from ..engine.labels import normalize_day
from .reader import RawRow
from .report import ReportBuilder
from .schema import MAX_ID_LEN, MAX_NAME_LEN

_ID_RE = re.compile(r"^\w[\w .\-]*$")
_WHOLE_RE = re.compile(r"^[+-]?\d+(\.0+)?$")
_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")
_TRUE = {"1", "true", "yes", "y", "t"}
_FALSE = {"0", "false", "no", "n", "f"}

BOOL_HELP = "Use 1/0, yes/no or true/false."


def parse_time(value: str) -> Optional[str]:
    """``9:05`` / ``09:05`` -> ``09:05``; ``None`` if not a 24-hour HH:MM time."""
    m = _TIME_RE.match(value.strip())
    if not m:
        return None
    hour, minute = int(m.group(1)), int(m.group(2))
    if hour > 23 or minute > 59:
        return None
    return f"{hour:02d}:{minute:02d}"


class Row:
    """Validates the cells of one CSV row and reports *every* problem found."""

    def __init__(self, rb: ReportBuilder, file: str, raw: RawRow, noun: str) -> None:
        self.rb = rb
        self.file = file
        self.raw = raw
        self.noun = noun  # "teacher", "room", ... used in messages
        self.errors = 0
        if raw.extra:
            self.error(
                None, ", ".join(raw.extra), "TOO_MANY_CELLS",
                f"This row has more cells than the header ({len(raw.extra)} extra: {', '.join(raw.extra)[:60]}).",
                "If a value contains a comma, wrap it in double quotes (for example \"Smith, J.\"), or delete the extra cells.",
            )

    @property
    def number(self) -> int:
        return self.raw.number

    @property
    def ok(self) -> bool:
        return self.errors == 0

    def get(self, field: str) -> str:
        return self.raw.cells.get(field, "")

    # -- issue helpers -----------------------------------------------------
    def error(self, field: Optional[str], value: Optional[str], code: str, message: str, fix: str) -> None:
        self.errors += 1
        self.rb.error(self.file, code, message, fix, row=self.number, field=field, value=value)

    def warn(self, field: Optional[str], value: Optional[str], code: str, message: str, fix: str) -> None:
        self.rb.warning(self.file, code, message, fix, row=self.number, field=field, value=value)

    def _missing(self, field: str) -> None:
        fix = f"Fill in the {self.noun}'s name." if field == "name" else f"Fill in {field} for this {self.noun}."
        self.error(field, "", "MISSING_FIELD", f"{field} is empty, but it is required.", fix)

    # -- typed accessors ---------------------------------------------------
    def text(self, field: str, *, required: bool = True, max_len: int = MAX_NAME_LEN) -> Optional[str]:
        value = self.get(field)
        if not value:
            if required:
                self._missing(field)
                return None
            return ""
        if len(value) > max_len:
            self.error(field, value[:40] + "...", "TOO_LONG",
                       f"{field} is {len(value)} characters long; the limit is {max_len}.",
                       f"Shorten {field} to {max_len} characters or fewer.")
            return None
        return value

    def ident(self, field: str) -> Optional[str]:
        """A required identifier: letters, digits, space, '-', '_' or '.' (max 40)."""
        value = self.text(field, max_len=MAX_ID_LEN)
        if value is None:
            return None
        if not _ID_RE.match(value):
            self.error(field, value, "INVALID_ID",
                       f"{field} '{value}' contains characters that are not allowed.",
                       "Use only letters, digits, spaces, '-', '_' and '.', starting with a letter or digit.")
            return None
        return value

    def whole(self, field: str, lo: int, hi: int, *, default: Optional[int] = None) -> Optional[int]:
        value = self.get(field)
        if not value:
            if default is not None:
                return default
            self._missing(field)
            return None
        if not _WHOLE_RE.match(value):
            self.error(field, value, "NOT_A_NUMBER", f"{field} '{value}' is not a whole number.",
                       f"Enter digits only, for example {max(lo, 1)}.")
            return None
        digits = value.split(".")[0].lstrip("+-")
        number = int(value.split(".")[0]) if len(digits) <= 9 else (10**9 if not value.startswith("-") else -(10**9))
        if number < lo or number > hi:
            self.error(field, value, "OUT_OF_RANGE", f"{field} {value} is out of range; it must be between {lo} and {hi}.",
                       f"Enter a number from {lo} to {hi}.")
            return None
        return number

    def choice(self, field: str, allowed: tuple[str, ...]) -> Optional[str]:
        value = self.get(field)
        if not value:
            self._missing(field)
            return None
        if value.lower() not in allowed:
            options = " or ".join(f"'{a}'" for a in allowed)
            self.error(field, value, "INVALID_CHOICE", f"{field} '{value}' is not allowed; it must be {options}.",
                       f"Use exactly {options}.")
            return None
        return value.lower()

    def boolean(self, field: str, *, default: Optional[bool] = None) -> Optional[bool]:
        value = self.get(field)
        if not value:
            if default is not None:
                return default
            self._missing(field)
            return None
        low = value.lower()
        if low in _TRUE:
            return True
        if low in _FALSE:
            return False
        self.error(field, value, "INVALID_CHOICE", f"{field} '{value}' is not a yes/no value.", BOOL_HELP)
        return None

    def day(self, field: str = "day") -> Optional[str]:
        """Canonical short day name (``Mon``), or ``None`` after reporting INVALID_DAY."""
        value = self.get(field)
        if not value:
            self._missing(field)
            return None
        canonical = normalize_day(value)
        if canonical is None:
            self.error(field, value, "INVALID_DAY", f"'{value}' is not a valid day name.",
                       "Use Mon, Tue, Wed, Thu, Fri, Sat or Sun.")
            return None
        return canonical

    def clock(self, field: str) -> Optional[str]:
        value = self.get(field)
        if not value:
            self._missing(field)
            return None
        parsed = parse_time(value)
        if parsed is None:
            self.error(field, value, "INVALID_TIME", f"{field} '{value}' is not a valid time.",
                       "Use 24-hour HH:MM, for example 09:00 or 14:30.")
            return None
        return parsed
