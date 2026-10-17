"""Small helpers for turning days / periods into teacher-friendly wording."""

from __future__ import annotations

from typing import Optional

DAY_FULL: dict[str, str] = {
    "Mon": "Monday",
    "Tue": "Tuesday",
    "Wed": "Wednesday",
    "Thu": "Thursday",
    "Fri": "Friday",
    "Sat": "Saturday",
    "Sun": "Sunday",
}

_ALIASES: dict[str, str] = {}
for _short, _full in DAY_FULL.items():
    _ALIASES[_short.lower()] = _short
    _ALIASES[_full.lower()] = _short
_ALIASES.update({"tues": "Tue", "thur": "Thu", "thurs": "Thu"})


def normalize_day(value: str) -> Optional[str]:
    """Map ``monday`` / ``MON`` / ``Mon.`` to ``Mon``; ``None`` if unknown."""
    return _ALIASES.get(str(value).strip().rstrip(".").lower())


def day_name(day: str) -> str:
    """``Mon`` -> ``Monday`` (unknown names are returned unchanged)."""
    return DAY_FULL.get(day, day)


def period_phrase(start: int, duration: int = 1) -> str:
    """``Period 3`` for one period, ``Periods 3-4`` for a multi-period block."""
    if duration <= 1:
        return f"Period {start}"
    return f"Periods {start}-{start + duration - 1}"
