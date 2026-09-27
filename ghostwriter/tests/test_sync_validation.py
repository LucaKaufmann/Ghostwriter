"""Validation regressions for the combined sync endpoint."""

from uuid import uuid4

import pytest


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
