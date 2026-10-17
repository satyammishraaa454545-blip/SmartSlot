"""Small helpers shared by the API tests."""

from __future__ import annotations

from typing import Any, Optional

from fastapi.testclient import TestClient


def load_sample(client: TestClient, kind: str = "feasible") -> int:
    r = client.post("/api/datasets/load-sample", params={"kind": kind})
    assert r.status_code == 201, r.text
    return r.json()["dataset"]["id"]


def generate(client: TestClient, dataset_id: int, **body: Any) -> dict[str, Any]:
    """POST generate and return the full response (``version`` + ``result``)."""
    r = client.post(f"/api/datasets/{dataset_id}/generate", json=body or None)
    assert r.status_code == 201, r.text
    return r.json()


def new_draft(client: TestClient, kind: str = "feasible", **body: Any) -> tuple[int, dict[str, Any]]:
    """(dataset_id, version detail) of a freshly generated draft."""
    did = load_sample(client, kind)
    return did, generate(client, did, **body)["version"]


def get_version(client: TestClient, version_id: int) -> dict[str, Any]:
    r = client.get(f"/api/versions/{version_id}")
    assert r.status_code == 200, r.text
    return r.json()


def snapshot(version: dict[str, Any]) -> list[tuple]:
    """Comparable view of a version's placements."""
    return sorted((e["session_id"], e["day"], e["start_period"], e["room_id"], e["teacher_id"]) for e in version["entries"])


def find_clash(entries: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Two single-period classes of the same teacher: moving A onto B's slot double-books the teacher."""
    by_teacher: dict[str, list[dict[str, Any]]] = {}
    for e in entries:
        if e["duration"] == 1:
            by_teacher.setdefault(e["teacher_id"], []).append(e)
    for _tid, mine in sorted(by_teacher.items()):
        for a in mine:
            for b in mine:
                if a["batch_id"] != b["batch_id"] and (a["day"], a["start_period"]) != (b["day"], b["start_period"]):
                    return a, b
    raise AssertionError("no clash candidate in this timetable")


def patch_entry(client: TestClient, version_id: int, entry_id: str, **body: Any):
    return client.patch(f"/api/versions/{version_id}/entries/{entry_id}", json=body)


def publish(client: TestClient, version_id: int, acknowledge: Optional[bool] = None):
    body = {"acknowledge_incomplete": acknowledge} if acknowledge is not None else None
    return client.post(f"/api/versions/{version_id}/publish", json=body)


def detail(response) -> dict[str, Any]:
    return response.json()["detail"]
