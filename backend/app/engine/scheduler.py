"""Constraint-based backtracking scheduler.

Pipeline of :func:`generate`:

1. expand requirements into sessions;
2. build each session's candidate slots (teacher free, suitable room free,
   consecutive teaching periods) - sessions with none are reported with the
   exact reason (:meth:`Problem.diagnose`);
3. static capacity analysis (:mod:`analysis`) removes sessions that provably
   cannot fit (teacher/batch/room overload) and explains them;
4. depth-first search with dynamic most-constrained-first variable ordering
   (fewest remaining slots, then longest, then busiest teacher), forward
   checking, soft-score value ordering, and set-style symmetry breaking between
   the interchangeable sessions of one requirement;
5. if the whole search space was exhausted without a full solution, the
   deepest partial schedule is topped up greedily and then improved by a
   bounded branch-and-bound that maximises the number of placed sessions; if a
   *limit* stopped the search the best partial found is returned as-is;
6. the independent validator re-checks the result before a status is chosen.

Hard constraints between sessions are encoded as bitmasks: every candidate
claims "cells" (resource, day, period) for its teacher, batch and room, and two
candidates conflict iff their masks intersect.

The search is deterministic for a fixed node limit.  A wall-clock limit is also
enforced; hitting it is machine dependent by nature.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from .analysis import analyze
from .candidates import Candidate, Problem, room_kind
from .expand import expand_sessions
from .explain import explain_unplaced
from .models import (
    Dataset,
    Entry,
    ScheduleResult,
    SearchStats,
    Session,
    UnscheduledItem,
)
from .soft import SoftState
from .validator import validate

DEFAULT_MAX_NODES = 200_000
DEFAULT_TIME_LIMIT_S = 10.0


@dataclass
class _Outcome:
    assignment: list[int]  # candidate id per variable, -1 = not placed
    complete: bool = False
    hit_limit: bool = False
    exhausted: bool = False
    nodes: int = 0


@dataclass
class _Model:
    """Flattened search model (parallel arrays for speed)."""

    sessions: list[Session]
    cand_ids: list[list[int]]  # per variable: global candidate ids
    c_day: list[int] = field(default_factory=list)
    c_start: list[int] = field(default_factory=list)
    c_room: list[int] = field(default_factory=list)
    c_mask: list[int] = field(default_factory=list)
    c_ident: list[int] = field(default_factory=list)  # (day, start, room) identity across sessions
    c_first: list[int] = field(default_factory=list)  # ordinal of first teaching period
    c_last: list[int] = field(default_factory=list)
    c_slack: list[int] = field(default_factory=list)  # spare seats in the room
    v_teacher: list[int] = field(default_factory=list)
    v_batch: list[int] = field(default_factory=list)
    v_sb: list[int] = field(default_factory=list)
    v_kind: list[str] = field(default_factory=list)
    v_dur: list[int] = field(default_factory=list)
    v_tload: list[int] = field(default_factory=list)
    v_group: list[int] = field(default_factory=list)
    n_teachers: int = 0
    n_batches: int = 0
    adjacent: list[bool] = field(default_factory=list)
    last_ordinal: int = 0
    n_days: int = 0


def _build_model(problem: Problem, kept: list[tuple[Session, list[Candidate]]]) -> _Model:
    lk = problem.lk
    days = len(problem.days)
    tpos = {p: i for i, p in enumerate(problem.teaching)}
    n_periods = max(len(tpos), 1)
    t_index = {tid: i for i, tid in enumerate(lk.teachers)}
    b_index = {bid: i for i, bid in enumerate(lk.batches)}
    n_t, n_b = len(t_index), len(b_index)

    def bit(resource: int, day: int, ordinal: int) -> int:
        return 1 << ((resource * days + day) * n_periods + ordinal)

    # Static difficulty order: fewest candidates, longest, busiest teacher.
    tload: dict[str, int] = {}
    for s, _ in kept:
        tload[s.teacher_id] = tload.get(s.teacher_id, 0) + s.duration
    kept = sorted(
        kept,
        key=lambda sc: (len(sc[1]), -sc[0].duration, -tload[sc[0].teacher_id], sc[0].requirement_index, sc[0].index),
    )

    m = _Model(sessions=[s for s, _ in kept], cand_ids=[])
    m.n_teachers, m.n_batches, m.n_days = n_t, n_b, days
    m.last_ordinal = len(tpos) - 1
    m.adjacent = [
        (i + 1 < len(problem.teaching) and problem.teaching[i + 1] == problem.teaching[i] + 1)
        for i in range(len(problem.teaching))
    ]
    sb_ids: dict[tuple[str, str], int] = {}
    for s, cands in kept:
        t, b = t_index[s.teacher_id], b_index[s.batch_id]
        size = lk.batches[s.batch_id].student_count
        m.v_teacher.append(t)
        m.v_batch.append(b)
        m.v_sb.append(sb_ids.setdefault((s.subject_id, s.batch_id), len(sb_ids)))
        m.v_kind.append(room_kind(s))
        m.v_dur.append(s.duration)
        m.v_tload.append(tload[s.teacher_id])
        m.v_group.append(s.requirement_index)
        ids: list[int] = []
        for di, start, ri in cands:
            mask = 0
            for i in range(s.duration):
                o = tpos[start + i]
                mask |= bit(t, di, o) | bit(n_t + b, di, o) | bit(n_t + n_b + ri, di, o)
            ids.append(len(m.c_mask))
            m.c_day.append(di)
            m.c_start.append(start)
            m.c_room.append(ri)
            m.c_mask.append(mask)
            m.c_ident.append((di * 1000 + start) * 100_000 + ri)
            m.c_first.append(tpos[start])
            m.c_last.append(tpos[start + s.duration - 1])
            m.c_slack.append(problem.rooms[ri].capacity - size)
        m.cand_ids.append(ids)
    return m


class _Search:
    def __init__(self, m: _Model, max_nodes: int, deadline: float) -> None:
        self.m = m
        self.max_nodes = max_nodes
        self.deadline = deadline
        n = len(m.sessions)
        self.n = n
        self.dom: list[list[int]] = [list(ids) for ids in m.cand_ids]
        self.umask: list[int] = []
        for ids in m.cand_ids:
            u = 0
            for c in ids:
                u |= m.c_mask[c]
            self.umask.append(u)
        self.assigned: list[int] = [-1] * n
        self.nodes = 0
        self.groups: dict[int, list[int]] = {}
        for v in range(n):
            self.groups.setdefault(m.v_group[v], []).append(v)
        self.gptr: dict[int, int] = {g: 0 for g in self.groups}
        self.soft = SoftState(m.n_teachers, m.n_batches, m.n_days, m.adjacent, m.last_ordinal)
        self.n_assigned = 0
        self.skipped = 0  # sessions deliberately left out during maximize()

    # -- soft state helpers ------------------------------------------------
    def _soft_args(self, v: int, c: int) -> tuple:
        m = self.m
        return (
            m.v_teacher[v], m.v_batch[v], m.v_sb[v], m.v_kind[v],
            m.c_day[c], m.c_first[c], m.c_last[c], m.c_room[c],
        )

    def order_values(self, v: int) -> list[int]:
        m, pen = self.m, self.soft.penalty
        t, b, sb, kind = m.v_teacher[v], m.v_batch[v], m.v_sb[v], m.v_kind[v]
        scored = [
            (pen(t, b, sb, kind, m.c_day[c], m.c_first[c], m.c_last[c], m.c_room[c], m.c_slack[c]), c)
            for c in self.dom[v]
        ]
        scored.sort()
        return [c for _, c in scored]

    # -- variable selection -----------------------------------------------------
    def select(self) -> int:
        """Most constrained *group representative* (lowest unassigned sibling)."""
        m = self.m
        best_v, best_key = -1, None
        for g, members in self.groups.items():
            k = self.gptr[g]
            if k >= len(members):
                continue
            v = members[k]
            key = (len(self.dom[v]), -m.v_dur[v], -m.v_tload[v], v)
            if best_key is None or key < best_key:
                best_v, best_key = v, key
        return best_v

    # -- assignment with forward checking -----------------------------------------
    def try_assign(
        self, v: int, c: int, excluded: set[int], allow_empty: bool = False
    ) -> Optional[dict[int, list[int]]]:
        """Give ``v`` the slot ``c`` and forward-check.

        ``excluded`` holds the slot identities already tried (and abandoned)
        for ``v`` at this node; the interchangeable siblings of ``v`` may not
        use them, so each *set* of slots for a requirement is explored once
        (symmetry breaking that does not restrict which slot is best).  With
        ``allow_empty`` a neighbour's domain may be wiped out (that session is
        then simply unplaceable) instead of rejecting ``c``.
        """
        m = self.m
        mask, group = m.c_mask[c], m.v_group[v]
        saved: dict[int, list[int]] = {}
        dom, umask, assigned, c_mask, c_ident = self.dom, self.umask, self.assigned, m.c_mask, m.c_ident
        for u in range(self.n):
            if u == v or assigned[u] != -1:
                continue
            sibling = m.v_group[u] == group
            if not sibling and not (umask[u] & mask):
                continue
            d = dom[u]
            if sibling and excluded:
                nd = [x for x in d if not (c_mask[x] & mask) and c_ident[x] not in excluded]
            else:
                nd = [x for x in d if not (c_mask[x] & mask)]
            if len(nd) != len(d):
                if not nd and not allow_empty:
                    for w, old in saved.items():
                        dom[w] = old
                    return None
                saved[u] = d
                dom[u] = nd
        assigned[v] = c
        self.soft.add(*self._soft_args(v, c))
        self.gptr[group] += 1
        self.n_assigned += 1
        return saved

    def undo(self, v: int, c: int, saved: dict[int, list[int]]) -> None:
        for w, old in saved.items():
            self.dom[w] = old
        self.assigned[v] = -1
        self.soft.remove(*self._soft_args(v, c))
        self.gptr[self.m.v_group[v]] -= 1
        self.n_assigned -= 1

    # -- depth-first search ---------------------------------------------------------
    def run(self) -> _Outcome:
        n = self.n
        if n == 0:
            return _Outcome(assignment=[], complete=True)
        best_depth = 0
        best = [-1] * n
        # frame: [variable, ordered candidates, next position, taken candidate,
        #         saved domains, identities of candidates already tried here]
        stack: list[list] = []

        def push() -> None:
            v = self.select()
            stack.append([v, self.order_values(v), 0, -1, None, set()])

        push()
        while stack:
            f = stack[-1]
            if f[3] != -1:
                self.undo(f[0], f[3], f[4])
                f[3], f[4] = -1, None
            advanced = False
            while f[2] < len(f[1]):
                c = f[1][f[2]]
                f[2] += 1
                if self.nodes >= self.max_nodes or time.perf_counter() >= self.deadline:
                    return _Outcome(best, hit_limit=True, nodes=self.nodes)
                self.nodes += 1
                saved = self.try_assign(f[0], c, f[5])
                f[5].add(self.m.c_ident[c])
                if saved is None:
                    continue
                f[3], f[4] = c, saved
                advanced = True
                break
            if not advanced:
                stack.pop()
                continue
            if self.n_assigned > best_depth:
                best_depth = self.n_assigned
                best = list(self.assigned)
            if self.n_assigned == n:
                return _Outcome(list(self.assigned), complete=True, nodes=self.nodes)
            push()
        return _Outcome(best, exhausted=True, nodes=self.nodes)

    # -- maximise the number of placed sessions --------------------------------------------
    def _upper_bound(self, skipped: int) -> int:
        """Most sessions that can still end up placed from the current node."""
        dead = 0
        for g, members in self.groups.items():
            k = self.gptr[g]
            if k < len(members) and not self.dom[members[k]]:
                dead += len(members) - k
        return self.n - skipped - dead

    def maximize(self, assignment: list[int], count: int) -> list[int]:
        """Branch and bound for the largest partial schedule, starting from a
        known one (``assignment`` with ``count`` placed).

        Used only after the strict search proved that no complete schedule
        exists.  Same machinery as :meth:`run`, but a session may also be
        *skipped* (last option; skipping a group's current session skips its
        remaining interchangeable siblings too).  Stops at the node / time
        limit and returns the best schedule found so far.
        """
        n = self.n
        best, best_assign = count, list(assignment)
        if best >= n:
            return best_assign
        self.skipped = 0
        stack: list[list] = []  # [var, options, pos, taken (-2 none, -1 skip), saved, tried, rem]

        def push() -> None:
            v = self.select()
            stack.append([v, self.order_values(v) + [-1], 0, -2, None, set(), 0])

        def remaining() -> bool:
            return any(self.gptr[g] < len(m) for g, m in self.groups.items())

        push()
        while stack:
            f = stack[-1]
            v, group = f[0], self.m.v_group[f[0]]
            if f[3] == -1:  # undo a skip
                self.gptr[group] -= f[6]
                self.skipped -= f[6]
            elif f[3] != -2:
                self.undo(v, f[3], f[4])
            f[3], f[4] = -2, None
            advanced = False
            while f[2] < len(f[1]):
                c = f[1][f[2]]
                f[2] += 1
                if self.nodes >= self.max_nodes or time.perf_counter() >= self.deadline:
                    return best_assign
                self.nodes += 1
                if c == -1:
                    members = self.groups[group]
                    f[6] = len(members) - self.gptr[group]
                    self.gptr[group] = len(members)
                    self.skipped += f[6]
                    f[3] = -1
                else:
                    saved = self.try_assign(v, c, f[5], allow_empty=True)
                    f[5].add(self.m.c_ident[c])
                    if saved is None:
                        continue
                    f[3], f[4] = c, saved
                advanced = True
                break
            if not advanced:
                stack.pop()
                continue
            if not remaining():
                if self.n_assigned > best:
                    best, best_assign = self.n_assigned, list(self.assigned)
                    if best >= n:
                        return best_assign
                continue
            if self._upper_bound(self.skipped) <= best:
                continue
            push()
        return best_assign

    # -- greedy top-up -------------------------------------------------------------------
    def greedy_fill(self, assignment: list[int]) -> list[int]:
        """Place leftover variables one by one in the best still-valid slot."""
        m = self.m
        soft = SoftState(m.n_teachers, m.n_batches, m.n_days, m.adjacent, m.last_ordinal)
        used = 0
        out = list(assignment)
        for v, c in enumerate(out):
            if c != -1:
                used |= m.c_mask[c]
                soft.add(*self._soft_args(v, c))
        for v in range(self.n):
            if out[v] != -1:
                continue
            t, b, sb, kind = m.v_teacher[v], m.v_batch[v], m.v_sb[v], m.v_kind[v]
            best: Optional[tuple[float, int]] = None
            for c in m.cand_ids[v]:
                if m.c_mask[c] & used:
                    continue
                p = soft.penalty(t, b, sb, kind, m.c_day[c], m.c_first[c], m.c_last[c], m.c_room[c], m.c_slack[c])
                if best is None or (p, c) < best:
                    best = (p, c)
            if best is not None:
                c = best[1]
                out[v] = c
                used |= m.c_mask[c]
                soft.add(*self._soft_args(v, c))
        return out


# --------------------------------------------------------------------------
def generate(
    dataset: Dataset,
    max_nodes: int = DEFAULT_MAX_NODES,
    time_limit_s: float = DEFAULT_TIME_LIMIT_S,
) -> ScheduleResult:
    """Generate a timetable.  Never labels an incomplete or invalid schedule complete."""
    t0 = time.perf_counter()
    problem = Problem(dataset)
    sessions = expand_sessions(dataset)

    # ---- static pre-analysis -----------------------------------------------------------
    reasons_of: dict[str, tuple[list[str], list[str], list[str]]] = {}
    with_cands: list[tuple[Session, list[Candidate]]] = []
    cand_of: dict[str, list[Candidate]] = {}
    for s in sessions:
        cands = problem.candidates(s)
        if not cands:
            diag = problem.diagnose(s)
            reasons_of[s.session_id] = (
                [r.text for r in diag],
                [r.code for r in diag],
                [r.hint for r in diag if r.hint],
            )
        else:
            with_cands.append((s, cands))
            cand_of[s.session_id] = cands

    analysis = analyze(problem, [s for s, _ in with_cands])
    for sid, d in analysis.dropped.items():
        reasons_of[sid] = (d.reasons, d.codes, d.hints)
    findings = [f.text for f in analysis.findings]
    static_total = len(reasons_of)
    kept_ids = {s.session_id for s in analysis.kept}
    kept = [(s, cand_of[s.session_id]) for s, _ in with_cands if s.session_id in kept_ids]

    # ---- search ----------------------------------------------------------------------------
    model = _build_model(problem, kept)
    search = _Search(model, max_nodes, t0 + time_limit_s)
    outcome = search.run()
    assignment = outcome.assignment
    if outcome.exhausted:
        # No complete schedule exists.  Top up the deepest partial found, then
        # try to improve on it with a bounded branch-and-bound.
        assignment = search.greedy_fill(assignment)
        assignment = search.maximize(assignment, sum(1 for c in assignment if c != -1))
        outcome.nodes = search.nodes

    entries_by_id: dict[str, Entry] = {}
    for v, c in enumerate(assignment):
        if c == -1:
            continue
        s = model.sessions[v]
        entries_by_id[s.session_id] = Entry(
            session_id=s.session_id,
            day=problem.days[model.c_day[c]],
            start_period=model.c_start[c],
            duration=s.duration,
            teacher_id=s.teacher_id,
            room_id=problem.rooms[model.c_room[c]].room_id,
            subject_id=s.subject_id,
            batch_id=s.batch_id,
        )
    entries = [entries_by_id[s.session_id] for s in sessions if s.session_id in entries_by_id]

    # ---- explain what is left -------------------------------------------------------------------
    unscheduled: list[UnscheduledItem] = []
    for s in sessions:
        if s.session_id in entries_by_id:
            continue
        if s.session_id in reasons_of:
            reasons, codes, hints = reasons_of[s.session_id]
        else:
            reasons, codes, hints = explain_unplaced(
                problem, s, cand_of[s.session_id], entries, hit_limit=outcome.hit_limit
            )
        unscheduled.append(UnscheduledItem(session=s, reasons=reasons, reason_codes=codes, hints=hints))

    # ---- independent validation + status ------------------------------------------------------------
    report = validate(dataset, entries, with_suggestions=False)
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    stats = SearchStats(
        nodes=outcome.nodes,
        elapsed_ms=elapsed_ms,
        hit_limit=outcome.hit_limit,
        exhausted=outcome.exhausted,
        max_nodes=max_nodes,
        time_limit_s=time_limit_s,
        total_sessions=len(sessions),
        scheduled_count=len(entries),
    )
    total, placed = len(sessions), len(entries)
    search_unplaced = len(unscheduled) - static_total

    if total == 0:
        status = "failed"
        message = "Nothing to schedule: the data contains no session requirements."
    elif not report.valid:
        status = "failed"
        message = (
            "Internal consistency check failed: the generated timetable broke hard constraints "
            f"({report.summary}). It has not been marked as valid."
        )
    elif not unscheduled and report.complete:
        status = "complete"
        message = f"Timetable generated: all {total} sessions are scheduled with no conflicts."
    else:
        status = "partial" if placed else "failed"
        parts = []
        if outcome.hit_limit:
            parts.append(
                "No complete solution found within the search limit "
                f"({outcome.nodes} nodes, {elapsed_ms / 1000:.1f}s). "
                f"{placed} of {total} sessions were placed; {search_unplaced} still need a slot. "
                "A solution may still exist - try a larger search limit."
            )
        elif not placed:
            parts.append(f"No timetable could be generated: none of the {total} sessions could be scheduled.")
        elif search_unplaced:
            parts.append(
                f"Partial timetable: {placed} of {total} sessions scheduled. The scheduler checked every "
                f"possible arrangement and none places all of them, so {search_unplaced} "
                f"session{'s' if search_unplaced != 1 else ''} could not be fitted in."
            )
        else:
            parts.append(f"Partial timetable: {placed} of {total} sessions scheduled.")
        if static_total:
            parts.append(
                f"{static_total} session{'s' if static_total != 1 else ''} cannot be scheduled with the "
                "current data (see the reasons for each)."
            )
        message = " ".join(parts)

    return ScheduleResult(
        status=status,  # type: ignore[arg-type]
        message=message,
        scheduled=entries,
        unscheduled=unscheduled,
        findings=findings,
        stats=stats,
        validation=report,
    )
