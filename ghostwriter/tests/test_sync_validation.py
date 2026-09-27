"""Validation regressions for the combined sync endpoint."""

from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, create_engine

from app.api.sync import router
from app.core import database, security


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Exercise the real route/auth against an empty, test-owned database."""
    engine = create_engine(
        f"sqlite:///{tmp_path / 'sync.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)
    # AUTH-01 owns a separate reference after fixing auth session lifetimes.
    if hasattr(security, "engine"):
        monkeypatch.setattr(security, "engine", engine)
    monkeypatch.setattr("app.api.sync.scheduler_module.get_all_schedules", lambda: [])
    app = FastAPI()
    app.include_router(router, prefix="/api/sync")
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        engine.dispose()


@pytest.mark.parametrize("value", ["not-a-uuid", f"{uuid4()},not-a-uuid"])
def test_invalid_digest_ids_return_422_before_sync_work(client, monkeypatch, value):
    def unexpected_config(*_args, **_kwargs):
        pytest.fail("Invalid digest IDs must be rejected before sync processing")

    monkeypatch.setattr("app.api.sync.get_or_create_config", unexpected_config)

    response = client.get("/api/sync", params={"digest_ids": value})

    assert response.status_code == 422
    assert "digest_ids" in response.json()["detail"]


@pytest.mark.parametrize("value", ["", " , , ", f" {uuid4()} , {uuid4()} , "])
def test_empty_and_whitespace_separated_digest_ids_are_accepted(client, value):
    response = client.get("/api/sync", params={"digest_ids": value})

    assert response.status_code == 200
    assert set(response.json()) == {"config", "feeds", "digests", "schedules"}


def test_duplicate_digest_ids_are_accepted(client):
    known_id = uuid4()

    response = client.get(
        "/api/sync",
        params={"digest_ids": f" {known_id} , {known_id} , "},
    )

    assert response.status_code == 200
