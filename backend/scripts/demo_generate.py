"""Generate a timetable from a sample dataset and print readable grids.

Usage (from the backend folder, with the virtualenv active)::

    python scripts/demo_generate.py                      # sample_data/feasible
    python scripts/demo_generate.py ../sample_data/infeasible
    python scripts/demo_generate.py --view teacher       # per-teacher grids
    python scripts/demo_generate.py --max-nodes 5        # show the search-limit message
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.engine import (  # noqa: E402
    Dataset,
    Entry,
    analytics,
    generate,
    load_dataset_from_dir,
)

CELL_W = 24


def short_teacher(name: str) -> str:
    return name.split()[-1]


def render_grid(ds: Dataset, entries: list[Entry], title: str, label) -> str:
    """Days x periods grid; ``label(entry)`` produces the text for one cell."""
    days = ds.config.days
    lines = [f"\n=== {title} ===", " " * 14 + "".join(d.center(CELL_W) for d in days)]
    cells: dict[tuple[str, int], str] = {}
    for e in entries:
        for i, p in enumerate(e.periods):
            cells[(e.day, p)] = label(e) if i == 0 else "   '' (continued)"
    for p in ds.config.periods:
        head = f"P{p.period} {p.start}"
        if p.is_break:
            lines.append(f"{head:<14}" + "~ break ~".center(CELL_W * len(days)))
            continue
        lines.append(f"{head:<14}" + "".join(cells.get((d, p.period), ".").ljust(CELL_W)[:CELL_W] for d in days))
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", nargs="?", default=str(BACKEND.parent / "sample_data" / "feasible"))
    ap.add_argument("--view", choices=["batch", "teacher", "room"], default="batch")
    ap.add_argument("--max-nodes", type=int, default=200_000)
    ap.add_argument("--time-limit", type=float, default=10.0)
    args = ap.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    ds = load_dataset_from_dir(args.path)
    result = generate(ds, max_nodes=args.max_nodes, time_limit_s=args.time_limit)

    subj = {s.subject_id: s for s in ds.subjects}
    teachers = {t.teacher_id: t for t in ds.teachers}
    print(f"Dataset: {ds.name}  (semester {ds.semester})")
    print(f"Status : {result.status.upper()}")
    print(f"Message: {result.message}")
    st = result.stats
    print(f"Stats  : {st.nodes} nodes, {st.elapsed_ms} ms, hit_limit={st.hit_limit}, exhausted={st.exhausted}")
    print(f"Check  : {result.validation.summary}")

    entries = sorted(result.scheduled, key=lambda e: (e.batch_id, e.day, e.start_period))
    if args.view == "batch":
        for b in ds.batches:
            mine = [e for e in entries if e.batch_id == b.batch_id]
            print(
                render_grid(
                    ds, mine, f"{b.name} ({b.student_count} students)",
                    lambda e: f"{e.subject_id} {short_teacher(teachers[e.teacher_id].name)} {e.room_id}",
                )
            )
    elif args.view == "teacher":
        for t in ds.teachers:
            mine = [e for e in entries if e.teacher_id == t.teacher_id]
            print(render_grid(ds, mine, t.name, lambda e: f"{subj[e.subject_id].name[:12]} {e.batch_id} {e.room_id}"))
    else:
        for r in ds.rooms:
            mine = [e for e in entries if e.room_id == r.room_id]
            print(render_grid(ds, mine, f"{r.name} (cap {r.capacity}, {r.room_type})", lambda e: f"{e.subject_id} {e.batch_id}"))

    if result.findings:
        print("\nFindings (capacity problems):")
        for f in result.findings:
            print(f"  - {f}")
    if result.unscheduled:
        print(f"\nUnscheduled sessions ({len(result.unscheduled)}):")
        for u in result.unscheduled:
            print(f"  * {u.session.session_id}")
            for r in u.reasons:
                print(f"      - {r}")
            for h in u.hints:
                print(f"      > fix: {h}")

    a = analytics(ds, result.scheduled)
    print("\nTeacher workload (periods/week):")
    for t in a.teachers:
        days = " ".join(f"{d}:{n}" for d, n in t.per_day.items())
        print(f"  {t.name:<12} {t.periods_per_week:>2}/{t.available_periods:<2} ({t.utilization_pct:>4}%)  {days}")
    print("Room utilization:")
    for r in a.rooms:
        print(f"  {r.name:<16} {r.periods_used:>2}/{r.available_periods:<2} ({r.utilization_pct:>4}%)")
    return 0 if result.status == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
