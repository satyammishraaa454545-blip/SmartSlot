"""Editing a draft: dry-run, reject-without-saving, valid moves, unschedule/place, suggestions."""

from __future__ import annotations

from fastapi.testclient import TestClient

from .api_helpers import detail, find_clash, get_version, new_draft, patch_entry, publish, snapshot


def test_clashing_move_is_rejected_explained_and_nothing_is_saved(client: TestClient) -> None:
    _, v = new_draft(client)
    a, b = find_clash(v["entries"])
    before = snapshot(get_version(client, v["id"]))

    r = patch_entry(client, v["id"], a["entry_id"], day=b["day"], start_period=b["start_period"])
    assert r.status_code == 409
    d = detail(r)
    assert d["code"] == "MOVE_REJECTED"
    assert "was not saved" in d["message"] and a["teacher_name"] in d["message"]
    assert d["valid"] is False
    assert d["entry"]["day"] == b["day"] and d["entry"]["start_period"] == b["start_period"]  # the proposed placement
    assert any(c["code"] == "TEACHER_OVERLAP" for c in d["conflicts"])
    assert d["affected_entries"] and any(e["entry_id"] == b["entry_id"] for e in d["affected_entries"])
    assert d["suggestions"], "the coordinator is offered valid alternatives"
    for s in d["suggestions"]:
        assert {"day", "start_period", "end_period", "room_id", "room_name", "label", "start_time"} <= set(s)

    after = get_version(client, v["id"])
    assert snapshot(after) == before  # NOTHING saved
    assert after["summary"]["status"] == "valid_complete"


def test_validate_move_is_a_dry_run_with_the_same_payload(client: TestClient) -> None:
    _, v = new_draft(client)
    a, b = find_clash(v["entries"])
    r = client.post(f"/api/versions/{v['id']}/entries/{a['entry_id']}/validate-move",
                    json={"day": b["day"], "start_period": b["start_period"]})
    assert r.status_code == 200
    m = r.json()
    assert set(m) == {"valid", "message", "entry", "conflicts", "affected_entries", "suggestions"}
    assert m["valid"] is False and m["message"] and m["conflicts"]
    ok = client.post(f"/api/versions/{v['id']}/entries/{a['entry_id']}/validate-move", json={"room_id": a["room_id"]})
    assert ok.json()["valid"] is True and ok.json()["conflicts"] == []


def test_valid_move_is_saved_and_the_timetable_stays_valid(client: TestClient) -> None:
    _, v = new_draft(client)
    target = next(e for e in v["entries"] if e["duration"] == 1)
    sugg = client.get(f"/api/versions/{v['id']}/entries/{target['entry_id']}/suggestions").json()
    assert sugg, "a free valid slot exists for a single-period class"
    s = sugg[0]
    r = patch_entry(client, v["id"], target["entry_id"], day=s["day"], start_period=s["start_period"], room_id=s["room_id"])
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["entry"]["day"] == s["day"] and out["entry"]["start_period"] == s["start_period"]
    assert out["entry"]["room_id"] == s["room_id"]
    assert out["version"]["summary"]["status"] == "valid_complete"
    assert out["version"]["validation"]["conflicts"] == []
    saved = next(e for e in get_version(client, v["id"])["entries"] if e["entry_id"] == target["entry_id"])
    assert (saved["day"], saved["start_period"], saved["room_id"]) == (s["day"], s["start_period"], s["room_id"])


def test_change_room_and_teacher_are_validated_too(client: TestClient) -> None:
    _, v = new_draft(client)
    lecture = next(e for e in v["entries"] if e["subject_type"] == "lecture")
    bad_room = patch_entry(client, v["id"], lecture["entry_id"], room_id="LAB1")
    assert bad_room.status_code == 409 and any(c["code"] == "ROOM_TYPE" for c in detail(bad_room)["conflicts"])
    unknown = patch_entry(client, v["id"], lecture["entry_id"], room_id="NOPE")
    assert unknown.status_code == 409 and any(c["code"] == "INVALID_REFERENCE" for c in detail(unknown)["conflicts"])
    small = patch_entry(client, v["id"], next(e for e in v["entries"] if e["batch_id"] == "CE-A" and e["duration"] == 1)["entry_id"],
                        room_id="R103")  # 48 seats for 60 students
    assert small.status_code == 409 and any(c["code"] == "ROOM_CAPACITY" for c in detail(small)["conflicts"])
    no_change = patch_entry(client, v["id"], lecture["entry_id"])
    assert no_change.status_code == 422 and detail(no_change)["code"] == "NOTHING_TO_CHANGE"
    assert patch_entry(client, v["id"], "NO-SUCH-1", day="Mon").status_code == 404
    assert patch_entry(client, 9999, lecture["entry_id"], day="Mon").status_code == 404


def test_move_outside_the_working_week_or_into_the_break_is_rejected(client: TestClient) -> None:
    _, v = new_draft(client)
    e = next(x for x in v["entries"] if x["duration"] == 1)
    brk = patch_entry(client, v["id"], e["entry_id"], start_period=4)
    assert brk.status_code == 409 and any(c["code"] == "BLOCKED_PERIOD" for c in detail(brk)["conflicts"])
    sat = patch_entry(client, v["id"], e["entry_id"], day="Sat")
    assert sat.status_code == 409 and any(c["code"] == "OUTSIDE_WORKING_HOURS" for c in detail(sat)["conflicts"])
    alias = client.post(f"/api/versions/{v['id']}/entries/{e['entry_id']}/validate-move",
                        json={"day": "monday", "start_period": 7}).json()
    assert alias["entry"]["day"] == "Mon"  # long / lower-case day names are normalised


def test_move_into_a_teacher_unavailable_slot_is_rejected(client: TestClient) -> None:
    _, v = new_draft(client)
    sharma = next(e for e in v["entries"] if e["teacher_id"] == "T01" and e["duration"] == 1)
    r = patch_entry(client, v["id"], sharma["entry_id"], day="Mon", start_period=3)  # Dr. Sharma is away Mon P3
    assert r.status_code == 409
    assert any(c["code"] == "TEACHER_UNAVAILABLE" for c in detail(r)["conflicts"])
    assert any("Dr. Sharma" in c["message"] for c in detail(r)["conflicts"])


def test_unschedule_then_place_back(client: TestClient) -> None:
    _, v = new_draft(client)
    e = v["entries"][5]
    r = client.post(f"/api/versions/{v['id']}/entries/{e['entry_id']}/unschedule")
    assert r.status_code == 200, r.text
    after = r.json()["version"]
    assert after["summary"]["scheduled"] == 59 and after["summary"]["unscheduled"] == 1
    assert after["summary"]["status"] == "valid_incomplete" and after["is_complete"] is False
    item = after["unscheduled"][0]
    assert item["session_id"] == e["entry_id"] and item["reasons"] and item["hints"]
    assert client.post(f"/api/versions/{v['id']}/entries/{e['entry_id']}/unschedule").status_code == 404

    sugg = client.get(f"/api/versions/{v['id']}/unscheduled/{e['entry_id']}/suggestions").json()
    assert sugg
    back = {"day": sugg[0]["day"], "start_period": sugg[0]["start_period"], "room_id": sugg[0]["room_id"]}
    dry = client.post(f"/api/versions/{v['id']}/unscheduled/{e['entry_id']}/validate-place", json=back)
    assert dry.status_code == 200 and dry.json()["valid"] is True
    placed = client.post(f"/api/versions/{v['id']}/unscheduled/{e['entry_id']}/place", json=back)
    assert placed.status_code == 200, placed.text
    final = placed.json()["version"]
    assert final["summary"]["status"] == "valid_complete" and final["unscheduled"] == [] and final["is_complete"] is True
    # placing something already placed is refused
    again = client.post(f"/api/versions/{v['id']}/unscheduled/{e['entry_id']}/place", json=back)
    assert again.status_code == 409


def test_invalid_placement_is_rejected_and_nothing_saved(client: TestClient) -> None:
    _, v = new_draft(client)
    e = v["entries"][0]
    client.post(f"/api/versions/{v['id']}/entries/{e['entry_id']}/unschedule")
    other = next(x for x in v["entries"] if x["batch_id"] == e["batch_id"] and x["entry_id"] != e["entry_id"])
    r = client.post(f"/api/versions/{v['id']}/unscheduled/{e['entry_id']}/place",
                    json={"day": other["day"], "start_period": other["start_period"], "room_id": "R103"})
    assert r.status_code == 409 and detail(r)["code"] == "MOVE_REJECTED"
    assert get_version(client, v["id"])["summary"]["unscheduled"] == 1
    assert client.post(f"/api/versions/{v['id']}/unscheduled/NOPE-1/place",
                       json={"day": "Mon", "start_period": 1, "room_id": "R101"}).status_code == 404
    assert client.get(f"/api/versions/{v['id']}/unscheduled/{other['entry_id']}/suggestions").status_code == 409
    assert client.get(f"/api/versions/{v['id']}/entries/NOPE-1/suggestions").status_code == 404


def test_unscheduled_suggestions_in_the_infeasible_case(client: TestClient) -> None:
    _, v = new_draft(client, "infeasible")
    sid = v["unscheduled"][0]["session_id"]
    r = client.get(f"/api/versions/{v['id']}/unscheduled/{sid}/suggestions")
    assert r.status_code == 200 and r.json() == []  # provably no free lab block: honest empty list


def test_editing_a_published_version_is_rejected_until_restored_to_a_draft(client: TestClient) -> None:
    _, v = new_draft(client)
    e = next(x for x in v["entries"] if x["duration"] == 1)
    assert publish(client, v["id"]).status_code == 200
    for r in (
        patch_entry(client, v["id"], e["entry_id"], day="Fri", start_period=7),
        client.post(f"/api/versions/{v['id']}/entries/{e['entry_id']}/validate-move", json={"day": "Fri"}),
        client.post(f"/api/versions/{v['id']}/entries/{e['entry_id']}/unschedule"),
    ):
        assert r.status_code == 409
        d = detail(r)
        assert d["code"] == "VERSION_NOT_EDITABLE" and "Restore it to a new draft" in d["message"]
    assert snapshot(get_version(client, v["id"])) == snapshot(v)
    draft = client.post(f"/api/versions/{v['id']}/restore").json()["version"]
    sugg = client.get(f"/api/versions/{draft['id']}/entries/{e['entry_id']}/suggestions").json()
    assert patch_entry(client, draft["id"], e["entry_id"], day=sugg[0]["day"], start_period=sugg[0]["start_period"],
                       room_id=sugg[0]["room_id"]).status_code == 200
    assert snapshot(get_version(client, v["id"])) == snapshot(v)  # the published one is still untouched
