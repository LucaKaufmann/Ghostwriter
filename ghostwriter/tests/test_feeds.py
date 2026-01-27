"""Tests for feed management endpoints."""

import os

import pytest
from fastapi.testclient import TestClient

# Set test environment before importing app
os.environ["DATA_DIR"] = "/tmp/ghostwriter_test"
os.environ["OUTPUT_DIR"] = "/tmp/ghostwriter_test_output"
os.environ["API_KEY"] = ""  # Disable auth for tests

from app.main import app


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


def test_list_feeds_empty(client):
    """Test listing feeds when none exist."""
    response = client.get("/feeds")
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
    response = client.post("/feeds", json=feed_data)
    assert response.status_code == 200
    data = response.json()
    assert data["url"] == feed_data["url"]
    assert data["title"] == feed_data["title"]
    assert "id" in data


def test_sync_feeds(client):
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
    response = client.post("/feeds/sync", json=feeds)
    assert response.status_code == 200
    data = response.json()
    assert data["synced"] == 2
