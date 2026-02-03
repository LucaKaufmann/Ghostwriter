"""Tests for feed management endpoints."""


def test_list_feeds_empty(client):
    """Test listing feeds when none exist."""
    response = client.get("/api/feeds")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_create_feed(client):
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


def test_sync_feeds(client):
    """Test syncing feeds."""
    from app.api import feeds as feeds_api
    from importlib import reload

    feeds_api = reload(feeds_api)
    feeds_api.validate_public_url = lambda *_args, **_kwargs: None
    feeds_api.sync_feeds.__globals__["validate_public_url"] = feeds_api.validate_public_url

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


def test_sync_feeds_unchanged_counts(client):
    """Test syncing feeds reports unchanged on no-op sync."""
    from app.api import feeds as feeds_api
    from importlib import reload

    feeds_api = reload(feeds_api)
    feeds_api.validate_public_url = lambda *_args, **_kwargs: None
    feeds_api.sync_feeds.__globals__["validate_public_url"] = feeds_api.validate_public_url

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

    first = client.post("/api/feeds/sync", json=feeds)
    assert first.status_code == 200
    assert first.json()["created"] == 2

    second = client.post("/api/feeds/sync", json=feeds)
    assert second.status_code == 200
    assert second.json()["unchanged"] == 2


def test_sync_feeds_rejects_invalid_url(client):
    from importlib import reload
    from app.api import feeds as feeds_api

    reload(feeds_api)

    feeds = [
        {
            "url": "file:///etc/passwd",
            "title": "Bad Feed",
            "mode": "raw",
        }
    ]

    response = client.post("/api/feeds/sync", json=feeds)
    assert response.status_code == 422
