"""Dataset endpoints: import (files / zip / samples), reading, templates, configuration, availability."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from app import settings

from .api_helpers import detail, generate, load_sample

SAMPLES = Path(__file__).resolve().parents[2] / "sample_data"


def csv_files(kind: str = "feasible", skip: tuple[str, ...] = ()) -> list[tuple[str, tuple[str, bytes, str]]]:
    return [("files", (p.name, p.read_bytes(), "text/csv")) for p in sorted((SAMPLES / kind).glob("*.csv"))
            if p.name not in skip]


# ---------------------------------------------------------------------------
# import
# ---------------------------------------------------------------------------
def test_health_and_docs(client: TestClient) -> None:
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").json()["info"]["title"] == "SmartSlot API"


def test_import_multipart_csvs_ok(client: TestClient) -> None:
    r = client.post("/api/datasets/import", files=csv_files(), data={"name": "Sem 3 CE", "semester": "3"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["can_generate"] is True
    assert body["import_report"]["status"] == "ok"
    ds = body["dataset"]
    assert ds["name"] == "Sem 3 CE" and ds["semester"] == "3" and ds["import_status"] == "ok"
    assert ds["counts"]["requirements"] == 15 and ds["total_sessions"] == 60 and ds["version_count"] == 0


def test_import_accepts_fields_named_after_the_files(client: TestClient) -> None:
    files = [(p.stem, ("whatever.csv", p.read_bytes(), "text/csv")) for p in sorted((SAMPLES / "feasible").glob("*.csv"))]
    r = client.post("/api/datasets/import", files=files, data={"name": "x", "semester": "3"})
    assert r.status_code == 201 and r.json()["import_report"]["status"] == "ok"


def test_import_zip(client: TestClient) -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for p in (SAMPLES / "feasible").glob("*.csv"):
            zf.write(p, p.name)
    r = client.post("/api/datasets/import", files=[("files", ("data.zip", buf.getvalue(), "application/zip"))],
                    data={"name": "zipped", "semester": "3"})
    assert r.status_code == 201 and r.json()["import_report"]["status"] == "ok"
    assert r.json()["dataset"]["counts"]["teachers"] == 6


def test_import_with_errors_is_stored_but_flagged_and_blocks_generation(client: TestClient) -> None:
    r = client.post("/api/datasets/import", files=csv_files("invalid"), data={"name": "bad", "semester": "3"})
    assert r.status_code == 201
    body = r.json()
    assert body["can_generate"] is False
    assert body["dataset"]["import_status"] == "has_errors" and body["dataset"]["error_count"] == 35
    issue = body["import_report"]["issues"][0]
    assert set(issue) == {"severity", "file", "row", "field", "value", "code", "message", "how_to_fix"}
    did = body["dataset"]["id"]
    g = client.post(f"/api/datasets/{did}/generate")
    assert g.status_code == 422
    d = detail(g)
    assert d["code"] == "IMPORT_HAS_ERRORS" and "35 import error" in d["message"] and d["error_count"] == 35
    assert client.get(f"/api/datasets/{did}/versions").json() == []  # nothing was created


def test_import_missing_files_and_no_files(client: TestClient) -> None:
    r = client.post("/api/datasets/import", files=csv_files(skip=("rooms.csv", "periods.csv")), data={"name": "partial"})
    assert r.status_code == 201
    codes = {(i["file"], i["code"]) for i in r.json()["import_report"]["issues"] if i["severity"] == "error"}
    assert {("rooms.csv", "MISSING_FILE"), ("periods.csv", "MISSING_FILE")} <= codes
    assert r.json()["can_generate"] is False
    none = client.post("/api/datasets/import", data={"name": "nothing"})
    assert none.status_code in (400, 422)
    assert detail(none)["message"]


def test_import_rejects_non_csv_and_oversize_files(client: TestClient, monkeypatch) -> None:
    files = csv_files(skip=("teachers.csv",)) + [("files", ("teachers.xlsx", b"PK\x03\x04binary", "application/octet-stream"))]
    r = client.post("/api/datasets/import", files=files, data={"name": "x"})
    codes = {i["code"] for i in r.json()["import_report"]["issues"]}
    assert {"NOT_CSV", "MISSING_FILE"} <= codes

    monkeypatch.setattr(settings, "MAX_FILE_BYTES", 100)
    r = client.post("/api/datasets/import", files=csv_files(), data={"name": "big"})
    assert r.status_code == 201
    assert "FILE_TOO_LARGE" in {i["code"] for i in r.json()["import_report"]["issues"]}
    assert r.json()["can_generate"] is False


def test_request_size_limit_returns_413(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(settings, "MAX_UPLOAD_REQUEST_BYTES", 5000)
    r = client.post("/api/datasets/import", files=[("files", ("teachers.csv", b"x" * 20000, "text/csv"))], data={"name": "x"})
    assert r.status_code == 413 and detail(r)["code"] == "REQUEST_TOO_LARGE"
    monkeypatch.setattr(settings, "MAX_JSON_REQUEST_BYTES", 100)
    r = client.put("/api/datasets/1/availability", json={"rules": [{"resource_id": "T01", "day": "Mon", "period": 1}] * 50})
    assert r.status_code == 413


# ---------------------------------------------------------------------------
# samples, list, get, delete
# ---------------------------------------------------------------------------
def test_load_samples_go_through_validation(client: TestClient) -> None:
    ok = client.post("/api/datasets/load-sample", params={"kind": "feasible"}).json()
    assert ok["import_report"]["status"] == "ok" and ok["dataset"]["source"] == "sample:feasible"
    assert ok["dataset"]["total_sessions"] == 60
    inf = client.post("/api/datasets/load-sample", params={"kind": "infeasible"}).json()
    assert inf["dataset"]["import_status"] == "ok" and inf["dataset"]["total_sessions"] == 66
    bad = client.post("/api/datasets/load-sample", params={"kind": "invalid"}).json()
    assert bad["dataset"]["import_status"] == "has_errors" and bad["import_report"]["error_count"] == 35
    assert client.post("/api/datasets/load-sample", params={"kind": "../etc"}).status_code == 422
    assert client.post("/api/datasets/load-sample").status_code == 422


def test_list_and_get_dataset(client: TestClient) -> None:
    a, b = load_sample(client, "feasible"), load_sample(client, "infeasible")
    listing = client.get("/api/datasets").json()
    assert [d["id"] for d in listing] == [b, a]  # newest first
    r = client.get(f"/api/datasets/{a}")
    assert r.status_code == 200
    d = r.json()
    assert [t["teacher_id"] for t in d["teachers"]] == ["T01", "T02", "T03", "T04", "T05", "T06"]  # file order
    assert d["days"] == ["Mon", "Tue", "Wed", "Thu", "Fri"]
    assert d["teaching_periods"] == [1, 2, 3, 5, 6, 7]
    assert any(p["is_break"] and p["period"] == 4 for p in d["periods"])
    assert d["import_report"]["status"] == "ok" and len(d["availability"]) == 13
    assert d["rooms"][0] == {"room_id": "R101", "name": "Room 101", "capacity": 65, "room_type": "classroom"}
    missing = client.get("/api/datasets/999")
    assert missing.status_code == 404 and detail(missing)["code"] == "DATASET_NOT_FOUND"


def test_delete_dataset_and_published_protection(client: TestClient) -> None:
    did = load_sample(client)
    version = generate(client, did)["version"]
    assert client.post(f"/api/versions/{version['id']}/publish").status_code == 200
    blocked = client.delete(f"/api/datasets/{did}")
    assert blocked.status_code == 409 and detail(blocked)["code"] == "DATASET_HAS_PUBLISHED_VERSION"
    assert client.delete(f"/api/datasets/{did}", params={"force": "true"}).status_code == 204
    assert client.get(f"/api/datasets/{did}").status_code == 404
    assert client.get(f"/api/versions/{version['id']}").status_code == 404  # cascaded
    other = load_sample(client)
    assert client.delete(f"/api/datasets/{other}").status_code == 204
    assert client.delete(f"/api/datasets/{other}").status_code == 404


# ---------------------------------------------------------------------------
# templates
# ---------------------------------------------------------------------------
def test_templates(client: TestClient) -> None:
    names = client.get("/api/templates").json()
    assert names == ["teachers", "subjects", "batches", "rooms", "requirements", "days", "periods", "availability"]
    r = client.get("/api/templates/teachers.csv")
    assert r.status_code == 200 and r.text.strip() == "teacher_id,name,department_id"
    assert "attachment" in r.headers["content-disposition"]
    assert client.get("/api/templates/nope.csv").status_code == 404
    z = client.get("/api/templates.zip")
    assert z.status_code == 200 and z.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(z.content)) as zf:
        assert len(zf.namelist()) == 8 and "availability.csv" in zf.namelist()


# ---------------------------------------------------------------------------
# configuration
# ---------------------------------------------------------------------------
def test_update_config_days_and_periods(client: TestClient) -> None:
    did = load_sample(client)
    periods = [
        {"period": 1, "start": "9:00", "end": "09:50"},
        {"period": 2, "start": "09:50", "end": "10:40"},
        {"period": 3, "start": "10:40", "end": "11:00", "is_break": True},
        {"period": 4, "start": "11:00", "end": "11:50"},
    ]
    r = client.put(f"/api/datasets/{did}/config", json={"days": ["Monday", "tue", "Sat"], "periods": periods})
    assert r.status_code == 200, r.text
    d = r.json()["dataset"]
    assert d["days"] == ["Mon", "Tue", "Sat"]
    assert d["periods"][0]["start"] == "09:00" and d["teaching_periods"] == [1, 2, 4]
    assert r.json()["warnings"]  # old availability refers to days/periods that are gone
    assert generate(client, did)["result"]["status"] in ("complete", "partial")


def test_update_config_validation(client: TestClient) -> None:
    did = load_sample(client)
    bad = client.put(f"/api/datasets/{did}/config", json={
        "days": ["Mon", "Mon", "Funday"],
        "periods": [{"period": 1, "start": "9am", "end": "08:00"}, {"period": 1, "start": "10:00", "end": "11:00"}],
    })
    assert bad.status_code == 422
    d = detail(bad)
    assert d["code"] == "INVALID_CONFIG" and len(d["errors"]) >= 4
    all_breaks = client.put(f"/api/datasets/{did}/config", json={
        "days": ["Mon"], "periods": [{"period": 1, "start": "09:00", "end": "10:00", "is_break": True}]})
    assert all_breaks.status_code == 422
    assert client.get(f"/api/datasets/{did}").json()["days"] == ["Mon", "Tue", "Wed", "Thu", "Fri"]  # nothing saved
    unknown_field = client.put(f"/api/datasets/{did}/config", json={"days": ["Mon"], "periods": [], "extra": 1})
    assert unknown_field.status_code == 422 and detail(unknown_field)["code"] == "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# availability
# ---------------------------------------------------------------------------
def avail(client: TestClient, did: int) -> set[tuple[str, str, int]]:
    return {(a["resource_id"], a["day"], a["period"]) for a in client.get(f"/api/datasets/{did}").json()["availability"]}


def test_availability_put_replaces_everything(client: TestClient) -> None:
    did = load_sample(client)
    r = client.put(f"/api/datasets/{did}/availability", json={"rules": [
        {"resource_id": "T01", "day": "Mon", "period": 1},
        {"resource_id": "LAB1", "day": "Tue", "period": 2, "available": False},
        {"resource_id": "T02", "day": "Wed", "period": 3, "available": True},  # default: not stored
    ]})
    assert r.status_code == 200, r.text
    assert avail(client, did) == {("T01", "Mon", 1), ("LAB1", "Tue", 2)}
    cleared = client.put(f"/api/datasets/{did}/availability", json={"rules": []})
    assert cleared.status_code == 200 and avail(client, did) == set()


def test_availability_patch_toggles_single_slots(client: TestClient) -> None:
    did = load_sample(client)
    before = avail(client, did)
    r = client.patch(f"/api/datasets/{did}/availability", json={"resource_id": "T02", "day": "Mon", "period": 2, "available": False})
    assert r.status_code == 200 and avail(client, did) == before | {("T02", "Mon", 2)}
    again = client.patch(f"/api/datasets/{did}/availability", json={"resource_id": "T02", "day": "Mon", "period": 2, "available": False})
    assert again.status_code == 200 and avail(client, did) == before | {("T02", "Mon", 2)}  # idempotent
    client.patch(f"/api/datasets/{did}/availability", json={"resource_id": "T02", "day": "Mon", "period": 2, "available": True})
    assert avail(client, did) == before
    bulk = client.patch(f"/api/datasets/{did}/availability/bulk", json={"changes": [
        {"resource_id": "T04", "day": "Fri", "period": 5, "available": False},
        {"resource_id": "T04", "day": "Fri", "period": 6, "available": False},
    ]})
    assert bulk.status_code == 200 and {("T04", "Fri", 5), ("T04", "Fri", 6)} <= avail(client, did)


def test_availability_validation_saves_nothing(client: TestClient) -> None:
    did = load_sample(client)
    before = avail(client, did)
    bad = client.put(f"/api/datasets/{did}/availability", json={"rules": [
        {"resource_id": "T01", "day": "Mon", "period": 1},
        {"resource_id": "NOBODY", "day": "Mon", "period": 1},
        {"resource_id": "T01", "day": "Sat", "period": 1},
        {"resource_id": "T01", "day": "Mon", "period": 99},
    ]})
    assert bad.status_code == 422
    d = detail(bad)
    assert d["code"] == "INVALID_AVAILABILITY"
    assert {e["index"] for e in d["errors"]} == {1, 2, 3}
    assert avail(client, did) == before
    bulk_bad = client.patch(f"/api/datasets/{did}/availability/bulk", json={"changes": [
        {"resource_id": "T01", "day": "Tue", "period": 1}, {"resource_id": "ZZ", "day": "Tue", "period": 1}]})
    assert bulk_bad.status_code == 422 and avail(client, did) == before  # all or nothing
    on_break = client.patch(f"/api/datasets/{did}/availability", json={"resource_id": "T01", "day": "Mon", "period": 4})
    assert on_break.status_code == 200 and on_break.json()["warnings"]


# ---------------------------------------------------------------------------
# light editing
# ---------------------------------------------------------------------------
def test_patch_room_teacher_batch(client: TestClient) -> None:
    did = load_sample(client)
    r = client.patch(f"/api/datasets/{did}/rooms/R103", json={"capacity": 70, "room_type": "classroom", "name": "Room 103 (big)"})
    assert r.status_code == 200
    room = next(x for x in r.json()["dataset"]["rooms"] if x["room_id"] == "R103")
    assert room == {"room_id": "R103", "name": "Room 103 (big)", "capacity": 70, "room_type": "classroom"}
    t = client.patch(f"/api/datasets/{did}/teachers/T01", json={"name": "Dr. Sharma Jr."})
    assert t.status_code == 200
    b = client.patch(f"/api/datasets/{did}/batches/CE-A", json={"student_count": 50})
    assert next(x for x in b.json()["dataset"]["batches"] if x["batch_id"] == "CE-A")["student_count"] == 50
    assert client.patch(f"/api/datasets/{did}/rooms/NOPE", json={"capacity": 5}).status_code == 404
    assert client.patch(f"/api/datasets/{did}/rooms/R103", json={}).status_code == 422
    assert client.patch(f"/api/datasets/{did}/rooms/R103", json={"capacity": 0}).status_code == 422
    assert client.patch(f"/api/datasets/{did}/rooms/R103", json={"room_type": "auditorium"}).status_code == 422


def test_streaming_upload_without_content_length_is_still_capped(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(settings, "MAX_UPLOAD_REQUEST_BYTES", 5000)

    def chunks():
        yield b'--b\r\nContent-Disposition: form-data; name="files"; filename="teachers.csv"\r\nContent-Type: text/csv\r\n\r\n'
        for _ in range(20):
            yield b"x" * 1000
        yield b"\r\n--b--\r\n"

    r = client.post("/api/datasets/import", content=chunks(), headers={"content-type": "multipart/form-data; boundary=b"})
    assert r.status_code == 413 and detail(r)["code"] == "REQUEST_TOO_LARGE"


def test_malformed_multipart_is_a_clear_400(client: TestClient) -> None:
    r = client.post("/api/datasets/import", content=b"not multipart at all",
                    headers={"content-type": "multipart/form-data; boundary=zzz"})
    assert r.status_code in (400, 422) and detail(r)["message"]


def test_too_many_files_in_one_upload(client: TestClient) -> None:
    files = [("files", (f"f{i}.csv", b"a\n1\n", "text/csv")) for i in range(settings.MAX_UPLOAD_FILES + 1)]
    r = client.post("/api/datasets/import", files=files, data={"name": "x"})
    assert r.status_code == 400 and detail(r)["code"] == "BAD_UPLOAD"
