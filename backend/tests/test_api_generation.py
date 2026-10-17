"""Generate endpoint: complete / partial / blocked, and the published version staying safe."""

from __future__ import annotations

from fastapi.testclient import TestClient

from .api_helpers import detail, generate, get_version, load_sample, publish, snapshot


def test_generate_feasible_is_complete_with_zero_conflicts(client: TestClient) -> None:
    did = load_sample(client, "feasible")
    out = generate(client, did)
    result, v = out["result"], out["version"]
    assert result["status"] == "complete"
    assert result["stats"]["scheduled_count"] == 60 == result["stats"]["total_sessions"]
    assert v["status"] == "draft" and v["is_complete"] is True and v["created_by"] == "coordinator"
    assert v["summary"] == {
        "total_sessions": 60, "scheduled": 60, "unscheduled": 0, "status": "valid_complete",
        "error_count": 0, "warning_count": 0, "needs_review_count": 0,
        "message": "Valid and complete: all 60 required sessions are scheduled with no conflicts.",
    }
    assert v["validation"]["valid"] and v["validation"]["complete"] and v["validation"]["conflicts"] == []
    assert v["unscheduled"] == [] and v["needs_review"] == []
    assert len(v["entries"]) == 60
    assert v["generation"]["status"] == "complete"


def test_entries_are_enriched_and_sorted(client: TestClient) -> None:
    v = generate(client, load_sample(client))["version"]
    entries = v["entries"]
    first = entries[0]
    for key in ("entry_id", "session_id", "day", "start_period", "end_period", "duration", "start_time", "end_time",
                "teacher_id", "teacher_name", "subject_id", "subject_name", "subject_type", "batch_id", "batch_name",
                "room_id", "room_name", "room_type", "needs_review"):
        assert key in first, key
    assert first["entry_id"] == first["session_id"]
    lab = next(e for e in entries if e["subject_type"] == "practical")
    assert lab["room_type"] == "lab" and lab["duration"] == 2 and lab["end_period"] == lab["start_period"] + 1
    assert lab["teacher_name"] == "Mr. Das" and lab["room_name"] == "Computer Lab 1"
    order = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4}
    keys = [(order[e["day"]], e["start_period"], e["batch_id"], e["session_id"]) for e in entries]
    assert keys == sorted(keys)
    # a practical never straddles the lunch break (period 4)
    assert all(not (e["start_period"] < 4 <= e["end_period"]) for e in entries)
    assert not any(e["start_period"] == 4 for e in entries)


def test_version_detail_carries_the_grid_config(client: TestClient) -> None:
    v = generate(client, load_sample(client))["version"]
    assert v["dataset"]["days"] == ["Mon", "Tue", "Wed", "Thu", "Fri"]
    assert [p["period"] for p in v["dataset"]["periods"]] == [1, 2, 3, 4, 5, 6, 7]
    assert v["dataset"]["periods"][3] == {"period": 4, "start": "11:30", "end": "12:20", "is_break": True}
    assert v["dataset"]["name"] and v["dataset"]["semester"] == "3"


def test_generate_infeasible_is_partial_with_reasons(client: TestClient) -> None:
    did = load_sample(client, "infeasible")
    out = generate(client, did)
    v, result = out["version"], out["result"]
    assert result["status"] == "partial"
    assert result["stats"]["hit_limit"] is False
    assert any("blocks" in f or "block" in f for f in result["findings"]) or result["findings"]
    assert v["summary"]["scheduled"] == 63 and v["summary"]["unscheduled"] == 3 and v["summary"]["total_sessions"] == 66
    assert v["summary"]["status"] == "valid_incomplete" and v["is_complete"] is False
    assert sorted(u["session_id"] for u in v["unscheduled"]) == ["CS291-CE-A-4", "CS291-CE-B-4", "CS291-CE-C-4"]
    for u in v["unscheduled"]:
        assert u["reasons"] and u["reason_codes"] and u["hints"]
        assert u["subject_name"] == "DS Lab" and u["teacher_name"] == "Mr. Das" and u["duration"] == 2
        assert "Mr. Das" in " ".join(u["reasons"]) or "Computer Lab 1" in " ".join(u["reasons"])
    assert v["validation"]["valid"] is True  # incomplete is not invalid
    assert {c["code"] for c in v["validation"]["conflicts"]} == {"MISSING_SESSION"}
    assert all(c["severity"] == "warning" for c in v["validation"]["conflicts"])


def test_generate_is_blocked_for_empty_or_broken_datasets(client: TestClient) -> None:
    bad = load_sample(client, "invalid")
    r = client.post(f"/api/datasets/{bad}/generate")
    assert r.status_code == 422 and detail(r)["code"] == "IMPORT_HAS_ERRORS"
    assert "Fix the CSV files" in detail(r)["message"]
    assert client.post("/api/datasets/12345/generate").status_code == 404


def test_generate_accepts_options_and_validates_them(client: TestClient) -> None:
    did = load_sample(client)
    out = generate(client, did, label="Morning run", notes="try 1", created_by="Prof. Rao", max_nodes=100_000, time_limit_s=5)
    v = out["version"]
    assert (v["label"], v["notes"], v["created_by"]) == ("Morning run", "try 1", "Prof. Rao")
    assert out["result"]["stats"]["max_nodes"] == 100_000 and out["result"]["stats"]["time_limit_s"] == 5
    assert client.post(f"/api/datasets/{did}/generate", json={"max_nodes": 0}).status_code == 422
    assert client.post(f"/api/datasets/{did}/generate", json={"surprise": 1}).status_code == 422
    # tiny search limit: must be reported honestly, never as proof of infeasibility
    tiny = generate(client, did, max_nodes=5)["result"]
    assert tiny["status"] != "complete" or tiny["stats"]["scheduled_count"] == 60


def test_generate_creates_numbered_drafts_and_lists_them(client: TestClient) -> None:
    did = load_sample(client)
    a = generate(client, did)["version"]
    b = generate(client, did)["version"]
    assert (a["seq"], b["seq"]) == (1, 2) and a["label"] == "Version 1" and b["label"] == "Version 2"
    listing = client.get(f"/api/datasets/{did}/versions").json()
    assert [v["id"] for v in listing] == [b["id"], a["id"]]  # newest first
    assert all(v["status"] == "draft" and v["summary"]["status"] == "valid_complete" for v in listing)
    assert "entries" not in listing[0]  # list view is light
    assert client.get(f"/api/datasets/{did}").json()["version_count"] == 2


def test_generation_is_deterministic(client: TestClient) -> None:
    did = load_sample(client)
    a, b = generate(client, did)["version"], generate(client, did)["version"]
    assert snapshot(a) == snapshot(b)


def test_regenerate_never_touches_the_published_version(client: TestClient) -> None:
    did = load_sample(client)
    v1 = generate(client, did)["version"]
    assert publish(client, v1["id"]).status_code == 200
    published_before = get_version(client, v1["id"])
    assert published_before["status"] == "published"

    v2 = generate(client, did)["version"]
    assert v2["id"] != v1["id"] and v2["status"] == "draft"

    after = get_version(client, v1["id"])
    assert after["status"] == "published"
    assert after["published_at"] == published_before["published_at"]
    assert snapshot(after) == snapshot(published_before)
    listing = client.get(f"/api/datasets/{did}/versions").json()
    assert [v["status"] for v in listing] == ["draft", "published"]
    assert client.get(f"/api/datasets/{did}").json()["published_version_id"] == v1["id"]
    # even a regenerate with a different outcome (availability changed) leaves it alone
    client.patch(f"/api/datasets/{did}/availability", json={"resource_id": "T01", "day": "Tue", "period": 1, "available": False})
    generate(client, did)
    assert snapshot(get_version(client, v1["id"])) == snapshot(published_before)
