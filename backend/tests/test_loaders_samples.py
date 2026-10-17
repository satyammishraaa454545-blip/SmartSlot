"""CSV loader and the shipped sample / template files."""

from __future__ import annotations

import csv

import pytest

from app.engine import DatasetLoadError, expand_sessions, load_dataset_from_dir
from app.engine.labels import normalize_day

from .helpers import SAMPLE_DIR

FILES = ["teachers", "subjects", "batches", "rooms", "requirements", "availability", "days", "periods"]


def test_feasible_matches_prd_scenario():
    ds = load_dataset_from_dir(SAMPLE_DIR / "feasible")
    assert ds.name == "feasible" and ds.semester == "3"
    assert [t.name for t in ds.teachers] == [
        "Dr. Sharma", "Prof. Iyer", "Dr. Mehta", "Ms. Kapoor", "Mr. Das", "Dr. Rao",
    ]
    assert {b.name: b.student_count for b in ds.batches} == {"CE-A": 60, "CE-B": 55, "CE-C": 45}
    assert len(expand_sessions(ds)) == 60
    ids = [s.session_id for s in expand_sessions(ds)]
    assert ids[0] == "CS201-CE-A-1" and len(ids) == len(set(ids))
    # period 4 is the lunch break
    assert [p.period for p in ds.config.periods if p.is_break] == [4]
    # Dr. Sharma unavailable Monday P3 and Friday afternoon
    off = {(a.day, a.period) for a in ds.availability if a.resource_id == "T01" and not a.available}
    assert off == {("Mon", 3), ("Fri", 5), ("Fri", 6), ("Fri", 7)}


def test_infeasible_differs_only_in_lab_requirements():
    f = load_dataset_from_dir(SAMPLE_DIR / "feasible")
    i = load_dataset_from_dir(SAMPLE_DIR / "infeasible")
    assert f.teachers == i.teachers and f.rooms == i.rooms and f.availability == i.availability
    diff = [(a, b) for a, b in zip(f.requirements, i.requirements, strict=True) if a != b]
    assert len(diff) == 3 and all(a.subject_id == "CS291" and b.sessions_per_week == 4 for a, b in diff)


def test_templates_are_header_only_and_match_samples():
    for name in FILES:
        with (SAMPLE_DIR / "templates" / f"{name}.csv").open(newline="", encoding="utf-8") as fh:
            rows = list(csv.reader(fh))
        assert len(rows) == 1, f"{name}.csv template must contain only the header"
        with (SAMPLE_DIR / "feasible" / f"{name}.csv").open(newline="", encoding="utf-8") as fh:
            assert next(csv.reader(fh)) == rows[0], f"{name}.csv header differs from sample"


def test_every_sample_folder_has_all_files():
    for kind in ("feasible", "infeasible", "invalid"):
        for name in FILES:
            assert (SAMPLE_DIR / kind / f"{name}.csv").is_file(), (kind, name)


def test_invalid_folder_is_documented_and_loader_rejects_it_with_location():
    assert (SAMPLE_DIR / "invalid" / "EXPECTED_ERRORS.md").is_file()
    with pytest.raises(DatasetLoadError, match=r"subjects\.csv, row 6"):
        load_dataset_from_dir(SAMPLE_DIR / "invalid")


def test_loader_reports_missing_file_and_bad_numbers(tmp_path):
    for name in FILES:
        (tmp_path / f"{name}.csv").write_text((SAMPLE_DIR / "templates" / f"{name}.csv").read_text())
    with pytest.raises(DatasetLoadError, match="days.csv has no rows"):
        load_dataset_from_dir(tmp_path)
    (tmp_path / "days.csv").write_text("day\nMon\n")
    (tmp_path / "periods.csv").write_text("period,start,end,is_break\n1,09:00,09:50,0\n")
    (tmp_path / "rooms.csv").write_text("room_id,name,capacity,room_type\nR1,Room 1,abc,classroom\n")
    with pytest.raises(DatasetLoadError, match=r"rooms\.csv, row 2"):
        load_dataset_from_dir(tmp_path)
    (tmp_path / "rooms.csv").unlink()
    with pytest.raises(DatasetLoadError, match="Missing required file: rooms.csv"):
        load_dataset_from_dir(tmp_path)


def test_availability_file_is_optional_and_day_names_are_normalized(tmp_path):
    src = SAMPLE_DIR / "feasible"
    for name in FILES:
        (tmp_path / f"{name}.csv").write_text((src / f"{name}.csv").read_text())
    (tmp_path / "availability.csv").unlink()
    (tmp_path / "days.csv").write_text("day\nmonday\nTUE\n")
    ds = load_dataset_from_dir(tmp_path)
    assert ds.availability == [] and ds.config.days == ["Mon", "Tue"]
    assert normalize_day("Thurs") == "Thu" and normalize_day("Funday") is None
