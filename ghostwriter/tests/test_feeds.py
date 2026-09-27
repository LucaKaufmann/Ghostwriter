"""Tests for feed management endpoints."""

import socket

import pytest


@pytest.fixture
def public_feed_dns(monkeypatch, block_real_network):
    """Give feed URL validation a public answer without querying real DNS."""
    def resolve(host, port, *args, **kwargs):
        assert host == "example.com"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.215.14", port))]

    monkeypatch.setattr(socket, "getaddrinfo", resolve)


def test_list_feeds_empty(client):
    """Test listing feeds when none exist."""
    response = client.get("/api/feeds")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_create_feed(client, public_feed_dns):
    """Test creating a new feed."""
    feed_data = {
        "url": "https://example.com/feed.xml",
        "title": "Test Feed",
        "mode": "raw",
        "is_active": True,
        "max_articles": 5,
    }
    response = client.post("/api/feeds", json=feed_data)
    assert response.status_code == 200
    data = response.json()
    assert data["url"] == feed_data["url"]
    assert data["title"] == feed_data["title"]
    assert "id" in data


def test_sync_feeds(client, public_feed_dns):
    """Legacy clients can report exact no-ops but cannot create feeds."""
    feeds = [
        {
            "url": "https://example.com/feed1.xml",
            "title": "Feed 1",
            "mode": "raw",
        },
        {
            "url": "https://example.com/feed2.xml",
            "title": "Feed 2",
            "mode": "summarize",
        },
    ]
    assert client.post("/api/feeds/sync", json=feeds).status_code == 409
    for feed in feeds:
        assert client.post("/api/feeds", json=feed).status_code == 200
    response = client.post("/api/feeds/sync", json=feeds)
    assert response.status_code == 200
    data = response.json()
    assert data["synced"] == 2
    assert data["unchanged"] == 2


def test_dns_failure_returns_validation_error_and_retry_succeeds(client, monkeypatch):
    """Create, update, and sync report failed DNS without writing feed changes."""
    resolved = set()

    def resolve(host, port, *args, **kwargs):
        if host not in resolved:
            raise socket.gaierror(socket.EAI_NONAME, "unresolved")
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.215.14", port))]

    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    create_url = "https://input-create.example/feed.xml"
    create_data = {"url": create_url, "title": "Initial"}

    failed_create = client.post("/api/feeds", json=create_data)
    assert failed_create.status_code == 422
    assert "Hostname could not be resolved" in failed_create.json()["detail"]
    assert create_url not in {feed["url"] for feed in client.get("/api/feeds").json()}

    resolved.add("input-create.example")
    created = client.post("/api/feeds", json=create_data)
    assert created.status_code == 200
    feed_id = created.json()["id"]

    resolved.remove("input-create.example")
    failed_update = client.put(f"/api/feeds/{feed_id}", json={"title": "Changed"})
    assert failed_update.status_code == 422
    assert "Hostname could not be resolved" in failed_update.json()["detail"]
    assert client.get(f"/api/feeds/{feed_id}").json()["title"] == "Initial"

    resolved.add("input-create.example")
    updated = client.put(f"/api/feeds/{feed_id}", json={"title": "Changed"},
                         headers={"If-Match": f'"{created.json()["version"]}"'})
    assert updated.status_code == 200
    assert updated.json()["title"] == "Changed"

    batch = [
        {"url": "https://input-batch-one.example/feed.xml", "title": "One"},
        {"url": "https://input-batch-two.example/feed.xml", "title": "Two"},
    ]
    resolved.add("input-batch-one.example")
    failed_sync = client.post("/api/feeds/sync", json=batch)
    assert failed_sync.status_code == 422
    assert "Hostname could not be resolved" in failed_sync.json()["detail"]
    urls = {feed["url"] for feed in client.get("/api/feeds").json()}
    assert not {item["url"] for item in batch} & urls

    resolved.add("input-batch-two.example")
    synced = client.post("/api/feeds/sync", json=batch)
    assert synced.status_code == 409
    urls = {feed["url"] for feed in client.get("/api/feeds").json()}
    assert not {item["url"] for item in batch} & urls
