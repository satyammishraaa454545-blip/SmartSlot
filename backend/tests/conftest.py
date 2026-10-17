"""Fixtures for the API tests: a TestClient wired to a throw-away SQLite file."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("SMARTSLOT_DB", str(tmp_path / "smartslot-test.db"))
    monkeypatch.setenv("SMARTSLOT_DEV", "1")
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
