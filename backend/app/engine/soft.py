"""Soft-constraint scoring used to order candidate slots in the search.

Soft constraints never override hard ones: the search only uses these
penalties to decide which *valid* slot to try first (lower = better), so the
first complete solution found tends to be a nice one.

Penalised (see docs/ARCHITECTURE.md "Soft scoring"):
  * a subject's sessions for one batch landing on the same day;
  * uneven daily load per batch (and per teacher);
  * more than 3 consecutive teaching periods in a row for a teacher;
  * gaps between a teacher's (or batch's) classes on the same day;
  * the last period of the day, a batch's first class starting late in the
    day, and (lightly) every period later in the day, so classes pack
    towards the morning;
  * using a different room from the one the batch already uses (stability),
    and wasting seats in an oversized room.
Lunch/other breaks do not count as a gap, but do interrupt a "consecutive" run.
"""

from __future__ import annotations

# Penalty weights.
W_SAME_SUBJECT_DAY = 50.0
W_BATCH_DAY_LOAD = 4.0
W_TEACHER_DAY_LOAD = 2.0
W_RUN_OVER_MAX = 25.0
MAX_RUN = 3
W_TEACHER_GAP = 5.0
W_BATCH_GAP = 3.0
W_LAST_PERIOD = 6.0
W_LATER_PERIOD = 0.5  # per teaching-period ordinal: compact days, start early
W_BATCH_LATE_START = 3.0  # per idle teaching period before a batch's first class of the day
W_ROOM_CHANGE = 2.0
W_ROOM_SLACK = 0.05


def _gap(mask: int, first: int, last: int) -> int:
    """Teaching periods between the new block [first..last] and the nearest
    existing class in ``mask`` (bit i = i-th teaching period); 0 if none."""
    if mask == 0:
        return 0
    best = None
    below = mask & ((1 << first) - 1)
    if below:
        best = first - below.bit_length()
    above = mask >> (last + 1)
    if above:
        k = (above & -above).bit_length() - 1
        best = k if best is None else min(best, k)
    return best or 0


class SoftState:
    """Incrementally maintained occupancy statistics for scoring."""

    def __init__(self, n_teachers: int, n_batches: int, n_days: int, adjacent: list[bool], last_ordinal: int) -> None:
        self.t_mask = [[0] * n_days for _ in range(n_teachers)]
        self.b_mask = [[0] * n_days for _ in range(n_batches)]
        self.sb_days: dict[tuple[int, int], int] = {}  # (subject-batch key, day) -> sessions
        self.room_use: dict[tuple[int, str], dict[int, int]] = {}  # (batch, kind) -> room -> count
        self.adjacent = adjacent  # adjacent[o]: ordinals o and o+1 are consecutive period numbers
        self.last_ordinal = last_ordinal

    @staticmethod
    def _block(first: int, last: int) -> int:
        return ((1 << (last + 1)) - 1) ^ ((1 << first) - 1)

    def add(self, teacher: int, batch: int, sb_key: int, kind: str, day: int, first: int, last: int, room: int) -> None:
        block = self._block(first, last)
        self.t_mask[teacher][day] |= block
        self.b_mask[batch][day] |= block
        self.sb_days[(sb_key, day)] = self.sb_days.get((sb_key, day), 0) + 1
        use = self.room_use.setdefault((batch, kind), {})
        use[room] = use.get(room, 0) + 1

    def remove(self, teacher: int, batch: int, sb_key: int, kind: str, day: int, first: int, last: int, room: int) -> None:
        block = self._block(first, last)
        self.t_mask[teacher][day] &= ~block
        self.b_mask[batch][day] &= ~block
        self.sb_days[(sb_key, day)] -= 1
        use = self.room_use[(batch, kind)]
        use[room] -= 1
        if not use[room]:
            del use[room]

    def _run(self, mask: int, first: int, last: int) -> int:
        lo, hi = first, last
        while lo > 0 and (mask >> (lo - 1)) & 1 and self.adjacent[lo - 1]:
            lo -= 1
        while hi < self.last_ordinal and (mask >> (hi + 1)) & 1 and self.adjacent[hi]:
            hi += 1
        return hi - lo + 1

    def penalty(
        self,
        teacher: int,
        batch: int,
        sb_key: int,
        kind: str,
        day: int,
        first: int,
        last: int,
        room: int,
        slack: int,
    ) -> float:
        tm = self.t_mask[teacher][day]
        bm = self.b_mask[batch][day]
        p = W_SAME_SUBJECT_DAY * self.sb_days.get((sb_key, day), 0)
        p += W_BATCH_DAY_LOAD * bm.bit_count() + W_TEACHER_DAY_LOAD * tm.bit_count()
        p += W_TEACHER_GAP * _gap(tm, first, last) + W_BATCH_GAP * _gap(bm, first, last)
        run = self._run(tm | self._block(first, last), first, last)
        if run > MAX_RUN:
            p += W_RUN_OVER_MAX * (run - MAX_RUN)
        if last == self.last_ordinal:
            p += W_LAST_PERIOD
        p += W_LATER_PERIOD * first
        if bm == 0:
            p += W_BATCH_LATE_START * first
        use = self.room_use.get((batch, kind))
        if use and room not in use:
            p += W_ROOM_CHANGE
        p += W_ROOM_SLACK * slack
        return p
