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
    """Test syncing feeds."""
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
    response = client.post("/api/feeds/sync", json=feeds)
    assert response.status_code == 200
    data = response.json()
    assert data["synced"] == 2
