"""CSV and PDF export."""

from __future__ import annotations

import csv
import io

import pytest
from fastapi.testclient import TestClient

from .api_helpers import detail, generate, load_sample, new_draft, publish


def parse_csv(response) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))


def test_csv_export_parses_back_and_matches_the_version(client: TestClient) -> None:
    _, v = new_draft(client)
    r = client.get(f"/api/versions/{v['id']}/export.csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert 'attachment; filename="smartslot-' in r.headers["content-disposition"]
    assert r.content.startswith(b"\xef\xbb\xbf")  # BOM so Excel reads UTF-8
    rows = parse_csv(r)
    assert len(rows) == 60 == len(v["entries"])
    assert list(rows[0]) == [
        "session_id", "batch_id", "batch_name", "subject_id", "subject_name", "session_type", "teacher_id",
        "teacher_name", "room_id", "room_name", "room_type", "day", "start_period", "end_period", "duration",
        "start_time", "end_time"]
    by_id = {row["session_id"]: row for row in rows}
    for e in v["entries"]:
        row = by_id[e["entry_id"]]
        assert (row["day"], int(row["start_period"]), int(row["end_period"]), int(row["duration"])) == (
            e["day"], e["start_period"], e["end_period"], e["duration"])
        assert (row["teacher_id"], row["teacher_name"], row["room_id"], row["room_name"]) == (
            e["teacher_id"], e["teacher_name"], e["room_id"], e["room_name"])
        assert (row["batch_id"], row["subject_id"], row["subject_name"], row["session_type"]) == (
            e["batch_id"], e["subject_id"], e["subject_name"], e["subject_type"])
        assert (row["start_time"], row["end_time"]) == (e["start_time"], e["end_time"])
    # same order as the timetable itself
    assert [row["session_id"] for row in rows] == [e["entry_id"] for e in v["entries"]]


def test_csv_export_only_contains_scheduled_classes(client: TestClient) -> None:
    _, v = new_draft(client, "infeasible")
    rows = parse_csv(client.get(f"/api/versions/{v['id']}/export.csv"))
    assert len(rows) == 63
    assert not {"CS291-CE-A-4", "CS291-CE-B-4", "CS291-CE-C-4"} & {r["session_id"] for r in rows}


def test_csv_export_defuses_spreadsheet_formulas() -> None:
    from app.export.csv_export import entries_to_csv
    from app.schemas import EntryOut

    e = EntryOut(entry_id="x", session_id="x", day="Mon", start_period=1, end_period=1, duration=1,
                 subject_id="S", subject_name="=HYPERLINK(\"http://evil\")", subject_type="lecture", batch_id="B",
                 batch_name="+1", teacher_id="T", teacher_name="@SUM(A1)", room_id="R", room_name="-2",
                 room_type="classroom")
    rows = list(csv.DictReader(io.StringIO(entries_to_csv([e]).decode("utf-8-sig"))))
    assert rows[0]["subject_name"].startswith("'=") and rows[0]["teacher_name"].startswith("'@")
    assert rows[0]["batch_name"].startswith("'+") and rows[0]["room_name"].startswith("'-")


def pdf_pages(content: bytes) -> list[str]:
    fitz = pytest.importorskip("pymupdf")
    doc = fitz.open(stream=content, filetype="pdf")
    return [page.get_text() for page in doc]


def test_pdf_export_is_a_real_landscape_pdf(client: TestClient) -> None:
    _, v = new_draft(client)
    r = client.get(f"/api/versions/{v['id']}/export.pdf", params={"view": "batch"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF-") and b"%%EOF" in r.content[-2048:]
    assert len(r.content) > 10_000
    assert 'filename="smartslot-' in r.headers["content-disposition"] and r.headers["content-disposition"].endswith('.pdf"')


def test_pdf_has_one_page_per_entity_with_the_required_content(client: TestClient) -> None:
    _, v = new_draft(client)
    pages = pdf_pages(client.get(f"/api/versions/{v['id']}/export.pdf", params={"view": "batch"}).content)
    assert len(pages) == 3  # CE-A, CE-B, CE-C
    for page, batch in zip(pages, ("CE-A", "CE-B", "CE-C"), strict=True):
        assert batch in page and "Semester 3" in page and "Version 1" in page
        assert "DRAFT" in page and "Generated" in page and "Break" in page
        for day in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday"):
            assert day in page
        assert "Period 1" in page and "Period 7" in page and "11:30 - 12:20" in page
        assert "DS Lab" in page and "Mr. Das" in page and "Computer Lab 1" in page
    teacher_pages = pdf_pages(client.get(f"/api/versions/{v['id']}/export.pdf", params={"view": "teacher"}).content)
    assert len(teacher_pages) == 6 and "Dr. Sharma" in teacher_pages[0]
    room_pages = pdf_pages(client.get(f"/api/versions/{v['id']}/export.pdf", params={"view": "room"}).content)
    assert len(room_pages) == 4 and any("Computer Lab 1" in p and "Laboratory" in p for p in room_pages)


def test_pdf_with_an_id_is_a_single_page_and_shows_published_status(client: TestClient) -> None:
    _, v = new_draft(client, "infeasible")
    publish(client, v["id"], acknowledge=True)
    r = client.get(f"/api/versions/{v['id']}/export.pdf", params={"view": "teacher", "id": "T05"})
    pages = pdf_pages(r.content)
    assert len(pages) == 1
    assert "Mr. Das" in pages[0] and "PUBLISHED" in pages[0] and "INCOMPLETE" in pages[0]
    assert "-T05" in r.headers["content-disposition"].lower().replace("t05", "T05") or "t05" in r.headers["content-disposition"]


def test_pdf_errors(client: TestClient) -> None:
    _, v = new_draft(client)
    assert client.get(f"/api/versions/{v['id']}/export.pdf", params={"view": "galaxy"}).status_code == 422
    r = client.get(f"/api/versions/{v['id']}/export.pdf", params={"view": "batch", "id": "NOPE"})
    assert r.status_code == 404 and detail(r)["code"] == "ENTITY_NOT_FOUND"
    assert client.get("/api/versions/9999/export.pdf").status_code == 404
    assert client.get("/api/versions/9999/export.csv").status_code == 404


def test_pdf_handles_a_saturday_and_a_longer_day(client: TestClient) -> None:
    did = load_sample(client)
    periods = [{"period": i, "start": f"{8 + i:02d}:00", "end": f"{8 + i:02d}:50", "is_break": i == 5} for i in range(1, 10)]
    assert client.put(f"/api/datasets/{did}/config", json={
        "days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"], "periods": periods}).status_code == 200
    v = generate(client, did)["version"]
    pages = pdf_pages(client.get(f"/api/versions/{v['id']}/export.pdf", params={"view": "batch"}).content)
    assert len(pages) == 3 and "Saturday" in pages[0] and "Period 9" in pages[0]
