"""Tests for push notification device registration endpoints."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client


def _register_user(client: TestClient) -> str:
    credentials = {"username": "admin", "password": "password123"}
    resp = client.post("/api/auth/register", json=credentials)
    if resp.status_code == 200:
        return resp.json()["access_token"]

    # Registration may be closed if another test ran first.
    login = client.post("/api/auth/login", json=credentials)
    assert login.status_code == 200, login.text
    return login.json()["access_token"]


def test_register_list_unregister_device(client):
    token = _register_user(client)
    headers = {"Authorization": f"Bearer {token}"}

    register_resp = client.post(
        "/api/notifications/devices",
        headers=headers,
        json={
            "device_id": "ios-test-device-1",
            "platform": "ios",
            "token": "deadbeef",
            "app_version": "1.0",
            "device_model": "iPhone",
        },
    )
    assert register_resp.status_code == 200, register_resp.text
    registered = register_resp.json()
    assert registered["device_id"] == "ios-test-device-1"
    assert registered["platform"] == "ios"
    assert registered["enabled"] is True
    assert "token" not in registered

    list_resp = client.get("/api/notifications/devices", headers=headers)
    assert list_resp.status_code == 200, list_resp.text
    devices = list_resp.json()
    assert len(devices) == 1
    assert devices[0]["device_id"] == "ios-test-device-1"

    unreg = client.delete("/api/notifications/devices/ios-test-device-1", headers=headers)
    assert unreg.status_code == 200, unreg.text

    list_resp2 = client.get("/api/notifications/devices", headers=headers)
    assert list_resp2.status_code == 200, list_resp2.text
    d = list_resp2.json()[0]
    assert d["enabled"] is False
    assert d["disabled_at"] is not None


def test_register_requires_token_and_device_id(client):
    token = _register_user(client)
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post(
        "/api/notifications/devices",
        headers=headers,
        json={"device_id": "", "platform": "ios", "token": "x"},
    )
    assert resp.status_code == 400

    resp2 = client.post(
        "/api/notifications/devices",
        headers=headers,
        json={"device_id": "d1", "platform": "ios", "token": ""},
    )
    assert resp2.status_code == 400
