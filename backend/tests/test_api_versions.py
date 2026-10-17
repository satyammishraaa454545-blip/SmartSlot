"""Publishing gates, archive/restore, compare, revalidation after availability changes."""

from __future__ import annotations

from fastapi.testclient import TestClient

from .api_helpers import detail, generate, get_version, load_sample, new_draft, patch_entry, publish, snapshot


# ---------------------------------------------------------------------------
# publish
# ---------------------------------------------------------------------------
def test_publish_a_valid_complete_draft(client: TestClient) -> None:
    did, v = new_draft(client)
    r = publish(client, v["id"])
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["version"]["status"] == "published" and out["version"]["status_label"] == "Published"
    assert out["version"]["is_complete"] is True and out["version"]["published_at"]
    assert out["archived_version_id"] is None and "published" in out["message"]
    assert client.get(f"/api/datasets/{did}").json()["published_version_id"] == v["id"]
    again = publish(client, v["id"])
    assert again.status_code == 409 and detail(again)["code"] == "ALREADY_PUBLISHED"


def test_publish_is_blocked_with_a_report_when_there_are_hard_conflicts(client: TestClient) -> None:
    did, v = new_draft(client)
    victim = next(e for e in v["entries"] if e["duration"] == 1)
    # the teacher becomes unavailable AFTER generation -> the draft now contains a hard conflict
    client.patch(f"/api/datasets/{did}/availability",
                 json={"resource_id": victim["teacher_id"], "day": victim["day"], "period": victim["start_period"], "available": False})
    r = publish(client, v["id"])
    assert r.status_code == 409
    d = detail(r)
    assert d["code"] == "PUBLISH_BLOCKED" and "must be fixed" in d["message"]
    assert d["validation"]["valid"] is False and d["validation"]["status"] == "invalid"
    assert any(c["code"] == "TEACHER_UNAVAILABLE" for c in d["validation"]["conflicts"])
    assert get_version(client, v["id"])["status"] == "draft"  # still a draft; no half-publish
    assert client.get(f"/api/datasets/{did}").json()["published_version_id"] is None


def test_incomplete_timetable_needs_explicit_acknowledgement(client: TestClient) -> None:
    did, v = new_draft(client, "infeasible")
    assert v["summary"]["unscheduled"] == 3
    for body in (None, {"acknowledge_incomplete": False}):
        r = client.post(f"/api/versions/{v['id']}/publish", json=body)
        assert r.status_code == 409
        d = detail(r)
        assert d["code"] == "ACKNOWLEDGE_INCOMPLETE" and d["unscheduled"] == 3 and d["total_sessions"] == 66
        assert "acknowledge_incomplete=true" in d["message"]
    assert get_version(client, v["id"])["status"] == "draft"
    ok = publish(client, v["id"], acknowledge=True)
    assert ok.status_code == 200
    pv = ok.json()["version"]
    assert pv["status"] == "published" and pv["is_complete"] is False and pv["status_label"] == "Published (incomplete)"
    assert "incomplete" in ok.json()["message"]


def test_publishing_a_new_version_archives_the_previous_and_keeps_it_recoverable(client: TestClient) -> None:
    did, v1 = new_draft(client)
    publish(client, v1["id"])
    v2 = generate(client, did)["version"]
    r = publish(client, v2["id"])
    assert r.status_code == 200 and r.json()["archived_version_id"] == v1["id"]
    old = get_version(client, v1["id"])
    assert old["status"] == "archived" and old["status_label"] == "Archived"
    assert snapshot(old) == snapshot(v1)  # content kept
    listing = client.get(f"/api/datasets/{did}/versions").json()
    assert sorted(v["status"] for v in listing) == ["archived", "published"]
    # archived versions cannot be published or edited directly; they are restored
    no = publish(client, v1["id"])
    assert no.status_code == 409 and detail(no)["code"] == "VERSION_NOT_EDITABLE"
    restored = client.post(f"/api/versions/{v1['id']}/restore")
    assert restored.status_code == 201
    draft = restored.json()["version"]
    assert draft["status"] == "draft" and draft["parent_version_id"] == v1["id"] and draft["source"] == "restored"
    assert snapshot(draft) == snapshot(v1) and draft["summary"]["status"] == "valid_complete"
    assert "restored from" in draft["label"]
    back = publish(client, draft["id"])
    assert back.status_code == 200 and back.json()["archived_version_id"] == v2["id"]


def test_restore_accepts_label_and_clones_unscheduled_notes(client: TestClient) -> None:
    _, v = new_draft(client, "infeasible")
    r = client.post(f"/api/versions/{v['id']}/restore", json={"label": "Try again", "created_by": "Dr. Rao", "notes": "n"})
    assert r.status_code == 201
    d = r.json()["version"]
    assert (d["label"], d["created_by"], d["notes"]) == ("Try again", "Dr. Rao", "n")
    assert [u["session_id"] for u in d["unscheduled"]] == [u["session_id"] for u in v["unscheduled"]]
    assert all(u["reasons"] for u in d["unscheduled"])
    assert client.post("/api/versions/9999/restore").status_code == 404


def test_restore_revalidates_against_the_current_data(client: TestClient) -> None:
    did, v = new_draft(client)
    publish(client, v["id"])
    e = next(x for x in v["entries"] if x["duration"] == 1)
    client.patch(f"/api/datasets/{did}/availability",
                 json={"resource_id": e["teacher_id"], "day": e["day"], "period": e["start_period"], "available": False})
    draft = client.post(f"/api/versions/{v['id']}/restore").json()["version"]
    assert draft["summary"]["status"] == "invalid"
    assert [r["entry_id"] for r in draft["needs_review"]] == [e["entry_id"]]
    assert publish(client, draft["id"]).status_code == 409


def test_delete_versions(client: TestClient) -> None:
    did, v1 = new_draft(client)
    v2 = generate(client, did)["version"]
    publish(client, v1["id"])
    blocked = client.delete(f"/api/versions/{v1['id']}")
    assert blocked.status_code == 409 and detail(blocked)["code"] == "CANNOT_DELETE_PUBLISHED"
    assert client.delete(f"/api/versions/{v2['id']}").status_code == 204
    assert client.get(f"/api/versions/{v2['id']}").status_code == 404
    assert client.delete(f"/api/versions/{v2['id']}").status_code == 404


# ---------------------------------------------------------------------------
# compare
# ---------------------------------------------------------------------------
def test_compare_reports_moved_added_removed_and_room_changes(client: TestClient) -> None:
    did, a = new_draft(client)
    b = client.post(f"/api/versions/{a['id']}/restore").json()["version"]
    singles = [e for e in b["entries"] if e["duration"] == 1]
    # 1) move one class
    moved = singles[0]
    s = client.get(f"/api/versions/{b['id']}/entries/{moved['entry_id']}/suggestions").json()
    mv = next(x for x in s if x["room_id"] == moved["room_id"] and (x["day"], x["start_period"]) != (moved["day"], moved["start_period"]))
    assert patch_entry(client, b["id"], moved["entry_id"], day=mv["day"], start_period=mv["start_period"]).status_code == 200
    # 2) remove one class
    removed = singles[3]
    assert client.post(f"/api/versions/{b['id']}/entries/{removed['entry_id']}/unschedule").status_code == 200
    # 3) change the room of one CE-C class (any classroom fits 45 students)
    rc = next(e for e in singles[4:] if e["batch_id"] == "CE-C" and e["entry_id"] not in (moved["entry_id"], removed["entry_id"]))
    other_room = next(r for r in ("R101", "R102", "R103") if r != rc["room_id"])
    res = patch_entry(client, b["id"], rc["entry_id"], room_id=other_room)
    room_changed = res.status_code == 200

    cmp = client.get(f"/api/versions/{a['id']}/compare/{b['id']}")
    assert cmp.status_code == 200
    c = cmp.json()
    assert c["from_version"]["id"] == a["id"] and c["to_version"]["id"] == b["id"]
    by_sid = {ch["session_id"]: ch for ch in c["changes"]}
    assert by_sid[moved["entry_id"]]["type"] == "moved"
    expected = (f"{moved['subject_id']} for {moved['batch_name']} moved {moved['day']} P{moved['start_period']} "
                f"→ {mv['day']} P{mv['start_period']}")
    assert by_sid[moved["entry_id"]]["text"] == expected
    assert by_sid[moved["entry_id"]]["before"]["day"] == moved["day"] and by_sid[moved["entry_id"]]["after"]["day"] == mv["day"]
    assert by_sid[removed["entry_id"]]["type"] == "removed" and by_sid[removed["entry_id"]]["after"] is None
    assert c["summary"]["moved"] == 1 and c["summary"]["removed"] == 1 and c["summary"]["added"] == 0
    if room_changed:
        assert by_sid[rc["entry_id"]]["type"] == "room_changed" and c["summary"]["room_changed"] == 1
    assert c["summary"]["unchanged"] == 60 - len(c["changes"])
    assert c["summary"]["changed_total"] == len(c["changes"])

    # reversed: the removed class is now an "added" one
    rev = client.get(f"/api/versions/{b['id']}/compare/{a['id']}").json()
    assert {ch["session_id"]: ch["type"] for ch in rev["changes"]}[removed["entry_id"]] == "added"
    same = client.get(f"/api/versions/{a['id']}/compare/{a['id']}").json()
    assert same["changes"] == [] and same["summary"]["unchanged"] == 60


def test_compare_rejects_other_datasets_and_unknown_versions(client: TestClient) -> None:
    _, a = new_draft(client)
    _, b = new_draft(client, "infeasible")
    r = client.get(f"/api/versions/{a['id']}/compare/{b['id']}")
    assert r.status_code == 422 and detail(r)["code"] == "DIFFERENT_DATASETS"
    assert client.get(f"/api/versions/{a['id']}/compare/9999").status_code == 404


def test_compare_text_for_two_different_generations_is_human_readable(client: TestClient) -> None:
    did = load_sample(client)
    a = generate(client, did)["version"]
    client.put(f"/api/datasets/{did}/availability", json={"rules": [
        {"resource_id": "T01", "day": d, "period": p} for d in ("Mon", "Tue") for p in (1, 2, 3)]})
    b = generate(client, did)["version"]
    c = client.get(f"/api/versions/{a['id']}/compare/{b['id']}").json()
    assert c["changes"], "a different availability produces a different timetable"
    for ch in c["changes"]:
        assert ch["text"] and ch["type"] in ("moved", "room_changed", "teacher_changed", "changed", "added", "removed")


# ---------------------------------------------------------------------------
# validate / revalidate / needs_review
# ---------------------------------------------------------------------------
def test_availability_change_then_revalidate_flags_needs_review_without_touching_the_published_version(client: TestClient) -> None:
    did, v = new_draft(client)
    publish(client, v["id"])
    before = snapshot(get_version(client, v["id"]))
    victim = next(e for e in v["entries"] if e["teacher_id"] == "T02" and e["duration"] == 1)

    clean = client.post(f"/api/versions/{v['id']}/revalidate").json()
    assert clean["needs_review"] == [] and clean["summary"]["status"] == "valid_complete"

    r = client.patch(f"/api/datasets/{did}/availability",
                     json={"resource_id": "T02", "day": victim["day"], "period": victim["start_period"], "available": False})
    assert r.status_code == 200

    rv = client.post(f"/api/versions/{v['id']}/revalidate")
    assert rv.status_code == 200
    body = rv.json()
    assert body["version_id"] == v["id"]
    assert [n["entry_id"] for n in body["needs_review"]] == [victim["entry_id"]]
    item = body["needs_review"][0]
    assert item["codes"] == ["TEACHER_UNAVAILABLE"] and item["messages"] and item["label"]
    assert body["summary"]["status"] == "invalid" and body["summary"]["needs_review_count"] == 1
    assert any(c["code"] == "TEACHER_UNAVAILABLE" and c["suggestions"] for c in body["validation"]["conflicts"])

    live = get_version(client, v["id"])
    assert live["status"] == "published"  # never silently changed
    assert snapshot(live) == before
    flagged = next(e for e in live["entries"] if e["entry_id"] == victim["entry_id"])
    assert flagged["needs_review"] is True and flagged["review_messages"]
    assert [n["entry_id"] for n in live["needs_review"]] == [victim["entry_id"]]
    assert sum(e["needs_review"] for e in live["entries"]) == 1
    listing = client.get(f"/api/datasets/{did}/versions").json()
    assert listing[0]["summary"]["status"] == "invalid" and listing[0]["summary"]["needs_review_count"] == 1

    # the fix path: restore -> move the flagged class -> publish
    draft = client.post(f"/api/versions/{v['id']}/restore").json()["version"]
    sugg = client.get(f"/api/versions/{draft['id']}/entries/{victim['entry_id']}/suggestions").json()
    assert sugg
    fix = patch_entry(client, draft["id"], victim["entry_id"], day=sugg[0]["day"], start_period=sugg[0]["start_period"],
                      room_id=sugg[0]["room_id"])
    assert fix.status_code == 200 and fix.json()["version"]["needs_review"] == []
    assert publish(client, draft["id"]).status_code == 200


def test_room_capacity_change_also_flags_entries(client: TestClient) -> None:
    did, v = new_draft(client)
    in_r101 = [e for e in v["entries"] if e["room_id"] == "R101"]
    assert in_r101
    client.patch(f"/api/datasets/{did}/rooms/R101", json={"capacity": 10})
    live = get_version(client, v["id"])
    assert live["summary"]["status"] == "invalid"
    flagged = {n["entry_id"] for n in live["needs_review"]}
    assert flagged and flagged <= {e["entry_id"] for e in in_r101}
    assert any("ROOM_CAPACITY" in n["codes"] for n in live["needs_review"])


def test_validate_endpoint_returns_summary_and_report(client: TestClient) -> None:
    _, v = new_draft(client, "infeasible")
    r = client.post(f"/api/versions/{v['id']}/validate")
    assert r.status_code == 200
    out = r.json()
    assert set(out) == {"version_id", "summary", "validation", "needs_review"}
    assert out["validation"]["status"] == "valid_incomplete" and out["validation"]["warning_count"] == 3
    assert out["validation"]["counts"] == {"MISSING_SESSION": 3}
    assert client.post("/api/versions/9999/validate").status_code == 404


# ---------------------------------------------------------------------------
# analytics
# ---------------------------------------------------------------------------
def test_analytics(client: TestClient) -> None:
    _, v = new_draft(client)
    r = client.get(f"/api/versions/{v['id']}/analytics")
    assert r.status_code == 200
    a = r.json()
    assert a["version_id"] == v["id"] and a["teaching_periods_per_week"] == 30
    teachers = {t["teacher_id"]: t for t in a["teachers"]}
    assert set(teachers) == {"T01", "T02", "T03", "T04", "T05", "T06"}
    das = teachers["T05"]
    assert das["name"] == "Mr. Das" and das["periods_per_week"] == 12 and das["sessions"] == 6
    assert set(das["per_day"]) == {"Mon", "Tue", "Wed", "Thu", "Fri"}
    assert 0 <= das["utilization_pct"] <= 100 and das["available_periods"] > 0
    rooms = {x["room_id"]: x for x in a["rooms"]}
    assert rooms["LAB1"]["periods_used"] == 12 and rooms["LAB1"]["room_type"] == "lab"
    batches = {b["batch_id"]: b for b in a["batches"]}
    assert batches["CE-A"]["periods_per_week"] == 5 + 4 + 4 + 5 + 4  # lecture periods + 2 labs x 2
    assert a["total_periods_scheduled"] == sum(b["periods_per_week"] for b in a["batches"])
    assert client.get("/api/versions/9999/analytics").status_code == 404
