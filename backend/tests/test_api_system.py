"""Dev reset, error shapes, CORS, request validation, atomic writes, database file handling."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import db, settings
from app.engine import Dataset, Teacher
from app.importer import ImportReport
from app.repo import datasets as dataset_repo

from .api_helpers import detail, generate, load_sample, new_draft


def test_dev_reset_wipes_and_optionally_loads_the_feasible_sample(client: TestClient) -> None:
    load_sample(client, "infeasible")
    new_draft(client)
    r = client.post("/api/dev/reset")
    assert r.status_code == 200 and r.json() == {"reset": True, "dataset": None}
    assert client.get("/api/datasets").json() == []
    r = client.post("/api/dev/reset", params={"sample": "feasible"})
    body = r.json()
    assert body["reset"] is True and body["dataset"]["id"] == 1 and body["dataset"]["total_sessions"] == 60
    assert body["dataset"]["import_status"] == "ok"
    assert len(client.get("/api/datasets").json()) == 1
    assert client.post("/api/dev/reset", params={"sample": "bogus"}).status_code == 422


def test_dev_reset_is_disabled_without_the_dev_flag(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    load_sample(client)
    monkeypatch.delenv("SMARTSLOT_DEV")
    r = client.post("/api/dev/reset")
    assert r.status_code == 404 and detail(r)["code"] == "DEV_ONLY"
    assert len(client.get("/api/datasets").json()) == 1  # nothing was wiped
    assert client.get("/api/health").json()["dev_mode"] is False


def test_errors_have_one_stable_shape(client: TestClient) -> None:
    for r in (
        client.get("/api/datasets/999"),
        client.get("/api/versions/999"),
        client.get("/api/nope"),
        client.post("/api/datasets/load-sample", params={"kind": "bogus"}),
        client.get("/api/datasets/not-a-number"),
        client.put("/api/datasets/1/config", json="x"),
        client.delete("/api/health"),
    ):
        assert r.status_code >= 400
        d = r.json()["detail"]
        assert isinstance(d["code"], str) and isinstance(d["message"], str) and d["message"]
    v = client.get("/api/datasets/999").json()["detail"]
    assert v["code"] == "DATASET_NOT_FOUND" and "999" in v["message"]
    bad = client.post("/api/datasets/1/generate", json={"max_nodes": "lots"}).json()["detail"]
    assert bad["code"] == "VALIDATION_ERROR" and bad["errors"][0]["field"] == "max_nodes"


def test_internal_errors_do_not_leak_details(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    did = load_sample(client)

    def boom(*_a, **_k):
        raise RuntimeError("secret internal detail /etc/passwd")

    monkeypatch.setattr("app.services.versions.generate", boom)
    quiet = TestClient(client.app, raise_server_exceptions=False)
    r = quiet.post(f"/api/datasets/{did}/generate")
    assert r.status_code == 500
    assert detail(r)["code"] == "INTERNAL_ERROR" and "secret" not in r.text
    assert client.get(f"/api/datasets/{did}/versions").json() == []  # nothing half-saved


def test_cors_allows_the_vite_dev_server_only(client: TestClient) -> None:
    for origin in ("http://localhost:5173", "http://127.0.0.1:5173"):
        r = client.options("/api/datasets", headers={"Origin": origin, "Access-Control-Request-Method": "POST"})
        assert r.status_code == 200 and r.headers["access-control-allow-origin"] == origin
        g = client.get("/api/health", headers={"Origin": origin})
        assert g.headers["access-control-allow-origin"] == origin
    other = client.get("/api/health", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in other.headers
    exp = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert exp.status_code == 200


def test_database_is_created_automatically(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "nested" / "dir" / "smartslot.db"
    monkeypatch.setenv("SMARTSLOT_DB", str(target))
    assert not target.parent.exists()
    from app.main import app

    with TestClient(app) as c:
        assert c.get("/api/health").status_code == 200
    assert target.is_file()
    con = sqlite3.connect(target)
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    con.close()
    assert {"datasets", "teachers", "subjects", "batches", "rooms", "requirements", "days", "periods", "availability",
            "timetable_versions", "timetable_entries", "version_unscheduled"} <= tables


def test_default_database_location_is_backend_data(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SMARTSLOT_DB", raising=False)
    assert settings.db_path() == settings.BACKEND_DIR / "data" / "smartslot.db"


def test_unique_constraints_per_dataset(client: TestClient) -> None:
    a, b = load_sample(client), load_sample(client)  # same ids in two datasets are fine
    conn = db.connect()
    try:
        assert conn.execute("SELECT COUNT(*) FROM teachers WHERE teacher_id = 'T01'").fetchone()[0] == 2
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO teachers VALUES (?, 'T01', 'Dup', '', 99)", (a,))
        with pytest.raises(sqlite3.IntegrityError):  # only one published version per dataset
            v1 = generate(client, a)["version"]["id"]
            v2 = generate(client, a)["version"]["id"]
            conn.execute("UPDATE timetable_versions SET status='published' WHERE id IN (?, ?)", (v1, v2))
        assert b != a
    finally:
        conn.close()


def test_dataset_insert_is_all_or_nothing(client: TestClient) -> None:
    conn = db.connect()
    try:
        broken = Dataset(name="x", teachers=[Teacher(teacher_id="T1", name="A"), Teacher(teacher_id="T1", name="B")])
        report = ImportReport(status="ok", error_count=0, warning_count=0)
        with pytest.raises(sqlite3.IntegrityError):
            dataset_repo.insert_dataset(conn, name="x", semester="", source="test", dataset=broken, report=report)
        assert conn.execute("SELECT COUNT(*) FROM datasets").fetchone()[0] == 0  # no half-saved dataset
        assert conn.execute("SELECT COUNT(*) FROM teachers").fetchone()[0] == 0
    finally:
        conn.close()


def test_failed_edit_leaves_the_database_untouched(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    did, v = new_draft(client)
    e = next(x for x in v["entries"] if x["duration"] == 1)
    sugg = client.get(f"/api/versions/{v['id']}/entries/{e['entry_id']}/suggestions").json()[0]

    def boom(*_a, **_k):
        raise sqlite3.OperationalError("disk full")

    with monkeypatch.context() as patched:
        patched.setattr("app.services.editing.version_repo.replace_entry", boom)
        quiet = TestClient(client.app, raise_server_exceptions=False)
        r = quiet.patch(f"/api/versions/{v['id']}/entries/{e['entry_id']}",
                        json={"day": sugg["day"], "start_period": sugg["start_period"], "room_id": sugg["room_id"]})
        assert r.status_code == 500
    again = client.get(f"/api/versions/{v['id']}").json()
    saved = next(x for x in again["entries"] if x["entry_id"] == e["entry_id"])
    assert (saved["day"], saved["start_period"], saved["room_id"]) == (e["day"], e["start_period"], e["room_id"])


def test_deleting_a_dataset_cascades_everything(client: TestClient) -> None:
    did, v = new_draft(client)
    client.post(f"/api/versions/{v['id']}/entries/{v['entries'][0]['entry_id']}/unschedule")
    assert client.delete(f"/api/datasets/{did}").status_code == 204
    conn = db.connect()
    try:
        for table in ("teachers", "subjects", "batches", "rooms", "requirements", "days", "periods", "availability",
                      "timetable_versions", "timetable_entries", "version_unscheduled"):
            assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0, table
    finally:
        conn.close()
