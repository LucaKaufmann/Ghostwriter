"""Tests for media retry endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlmodel import Session

from app.core.database import engine
from app.models.media_feed import MediaFeed
from app.models.media_item import MediaItem


def _create_media_item(*, content_type: str, status: str) -> MediaItem:
    """Create and persist a media feed + media item for testing."""
    suffix = str(uuid4())[:8]
    feed = MediaFeed(
        feed_type=content_type,
        url=f"https://example.com/{content_type}/{suffix}",
        title=f"{content_type.title()} Feed {suffix}",
        is_active=True,
        mode="summarize",
        max_items=5,
    )
    item = MediaItem(
        media_feed_id=feed.id,
        guid=f"guid-{suffix}",
        url=f"https://example.com/{content_type}/item/{suffix}",
        title=f"{content_type.title()} Item {suffix}",
        author="Tester",
        content="sample content",
        content_type=content_type,
        mode="summarize",
        word_count=2,
        status=status,
        error_message="temporary failure" if status == "failed" else None,
        processing_ms=123 if status == "failed" else 0,
        completed_at=datetime.now(timezone.utc) if status == "failed" else None,
    )

    with Session(engine) as session:
        session.add(feed)
        session.commit()
        session.refresh(feed)
        item.media_feed_id = feed.id
        session.add(item)
        session.commit()
        session.refresh(item)
        return item


def test_retry_single_failed_item_sets_pending_and_clears_error(client):
    """Retrying a failed item should queue it and clear failure state."""
    item = _create_media_item(content_type="podcast", status="failed")

    stale_created_at = datetime.now(timezone.utc) - timedelta(hours=5)
    with Session(engine) as session:
        stale_item = session.get(MediaItem, item.id)
        assert stale_item is not None
        stale_item.created_at = stale_created_at
        session.add(stale_item)
        session.commit()

    response = client.post(f"/api/media/items/{item.id}/retry")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "queued"
    assert payload["item_id"] == str(item.id)

    with Session(engine) as session:
        refreshed = session.get(MediaItem, item.id)
        assert refreshed is not None
        assert refreshed.status == "pending"
        assert refreshed.error_message is None
        assert refreshed.processing_ms == 0
        assert refreshed.completed_at is None
        assert refreshed.created_at > stale_created_at.replace(tzinfo=None)


def test_retry_single_non_failed_returns_409(client):
    """Retrying a non-failed item should return conflict."""
    item = _create_media_item(content_type="podcast", status="pending")

    response = client.post(f"/api/media/items/{item.id}/retry")
    assert response.status_code == 409
    assert "Only failed media items can be retried" in response.json()["detail"]


def test_retry_single_missing_returns_404(client):
    """Retrying a missing item should return not found."""
    response = client.post(f"/api/media/items/{uuid4()}/retry")
    assert response.status_code == 404
    assert response.json()["detail"] == "Media item not found"


def test_retry_bulk_failed_by_content_type_requeues_only_matching(client):
    """Bulk retry should only re-queue failed items matching requested type."""
    failed_podcast = _create_media_item(content_type="podcast", status="failed")
    failed_youtube = _create_media_item(content_type="youtube", status="failed")

    response = client.post("/api/media/items/retry-failed", json={"content_type": "podcast"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["retried"] >= 1
    assert payload["skipped"] == 0

    with Session(engine) as session:
        refreshed_podcast = session.get(MediaItem, failed_podcast.id)
        refreshed_youtube = session.get(MediaItem, failed_youtube.id)
        assert refreshed_podcast is not None
        assert refreshed_youtube is not None
        assert refreshed_podcast.status == "pending"
        assert refreshed_youtube.status == "failed"


def test_retry_bulk_when_no_failed_returns_zero_counts(client):
    """Bulk retry returns zero after all matching failed items are already retried."""
    _create_media_item(content_type="youtube", status="failed")

    first = client.post("/api/media/items/retry-failed", json={"content_type": "youtube"})
    assert first.status_code == 200
    assert first.json()["retried"] >= 1

    second = client.post("/api/media/items/retry-failed", json={"content_type": "youtube"})
    assert second.status_code == 200
    payload = second.json()
    assert payload["retried"] == 0
    assert payload["skipped"] == 0
