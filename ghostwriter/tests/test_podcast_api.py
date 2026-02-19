"""Tests for podcast digest APIs and scheduling behavior."""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4
import xml.etree.ElementTree as ET

import pytest
from PIL import Image
from sqlmodel import Session, select

from app.core.auth import generate_api_token, get_token_prefix, hash_api_token
from app.core.database import engine
from app.models.api_token import APIToken
from app.models.digest import Digest, DigestArticle
from app.models.feed import Feed
from app.models.podcast_episode import PodcastEpisode
from app.models.user import User
from app.services.podcast_service import (
    AudioGenerationResult,
    PodcastGenerationPreferences,
    podcast_service,
)


def _create_digest_with_articles(
    *,
    article_count: int = 3,
    completed_at: datetime | None = None,
) -> tuple[UUID, list[UUID]]:
    suffix = str(uuid4())[:8]
    created = completed_at or datetime.utcnow()
    feed = Feed(
        url=f"https://example.com/feed/{suffix}.xml",
        title=f"Feed {suffix}",
        is_active=True,
        mode="raw",
        max_articles=5,
    )
    digest = Digest(
        filename=f"digest-{suffix}.epub",
        period="manual",
        status="completed",
        stage="completed",
        article_count=article_count,
        created_at=created,
        completed_at=created,
    )

    with Session(engine) as session:
        session.add(feed)
        session.commit()
        session.refresh(feed)

        session.add(digest)
        session.commit()
        session.refresh(digest)

        articles: list[DigestArticle] = []
        for index in range(article_count):
            article = DigestArticle(
                digest_id=digest.id,
                feed_id=feed.id,
                title=f"Article {index} {suffix}",
                url=f"https://example.com/articles/{suffix}/{index}",
                mode="raw",
                word_count=120,
                ai_failed=False,
                processing_ms=10,
                content=(
                    f"OpenAI and Apple update {index}. "
                    "This article covers AI developments and product news."
                ),
                author="Reporter",
                feed_title=feed.title,
                sort_order=index,
                content_type="article",
            )
            session.add(article)
            articles.append(article)

        session.commit()
        for article in articles:
            session.refresh(article)

        digest_id = digest.id
        article_ids = [article.id for article in articles]

    return digest_id, article_ids


def _create_episode(
    *,
    digest_id: UUID,
    article_ids: list[UUID],
    status: str,
    audio_path: Path | None = None,
) -> PodcastEpisode:
    now = datetime.utcnow()
    episode = PodcastEpisode(
        digest_id=digest_id,
        user_id=None,
        script="[HOST_A]: Intro\n[HOST_B]: Reply\n[HOST_A]: Outro\n[HOST_B]: End\n"
        "[HOST_A]: Next\n[HOST_B]: Done",
        audio_path=str(audio_path) if audio_path else None,
        audio_size_bytes=audio_path.stat().st_size if audio_path and audio_path.exists() else None,
        duration_seconds=95 if audio_path else None,
        article_ids=[str(article_id) for article_id in article_ids],
        article_count=len(article_ids),
        generation_cost_cents=41 if audio_path else None,
        status=status,
        error_message="generation failed" if status == "failed" else None,
        created_at=now,
        updated_at=now,
        started_at=now,
        completed_at=now if status == "ready" else None,
    )
    with Session(engine) as session:
        session.add(episode)
        session.commit()
        session.refresh(episode)
    return episode


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Create an API token and return auth headers for protected endpoints."""
    with Session(engine) as session:
        user = session.exec(select(User).order_by(User.created_at.asc())).first()
        if user is None:
            # Setup mode: endpoints are intentionally open when no users exist.
            return {}

        raw_token = generate_api_token()
        token_row = APIToken(
            user_id=user.id,
            name=f"podcast-test-{str(uuid4())[:8]}",
            token_hash=hash_api_token(raw_token),
            token_prefix=get_token_prefix(raw_token),
        )
        session.add(token_row)
        session.commit()

    return {"X-API-Key": raw_token}


def test_podcast_preferences_get_and_update(client, auth_headers):
    response = client.get("/api/podcast/preferences", headers=auth_headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["enabled"] is False
    assert payload["schedule"] == "manual"
    assert payload["preferred_length_minutes"] == 15
    assert payload["tts_provider"] == "openai"
    assert payload["openai_tts_model"] == "tts-1"

    update = client.put(
        "/api/podcast/preferences",
        json={
            "enabled": True,
            "schedule": "weekly",
            "schedule_time": "09:30",
            "schedule_day": "friday",
            "style": "formal",
            "boost_keywords": ["AI", "Swift", "AI"],
            "filter_keywords": ["crypto"],
            "tts_provider": "elevenlabs",
            "elevenlabs_model_id": "eleven_flash_v2_5",
            "elevenlabs_output_format": "mp3_44100_128",
            "elevenlabs_api_key": "xi-test-key",
            "host_a_voice": "nova",
            "host_b_voice": "echo",
            "podcast_feed_enabled": True,
            "podcast_feed_title": "My Test Feed",
        },
        headers=auth_headers,
    )
    assert update.status_code == 200
    updated = update.json()
    assert updated["enabled"] is True
    assert updated["schedule"] == "weekly"
    assert updated["schedule_time"] == "09:30"
    assert updated["schedule_day"] == "friday"
    assert updated["style"] == "formal"
    assert updated["tts_provider"] == "elevenlabs"
    assert updated["elevenlabs_model_id"] == "eleven_flash_v2_5"
    assert updated["elevenlabs_output_format"] == "mp3_44100_128"
    assert updated["boost_keywords"] == ["AI", "Swift"]
    assert updated["podcast_feed_enabled"] is True
    assert updated["podcast_feed_title"] == "My Test Feed"

    invalid = client.put(
        "/api/podcast/preferences",
        json={"schedule_time": "99:99"},
        headers=auth_headers,
    )
    assert invalid.status_code == 400
    assert "schedule_time" in invalid.json()["detail"]

    invalid_provider = client.put(
        "/api/podcast/preferences",
        json={"tts_provider": "unknown-provider"},
        headers=auth_headers,
    )
    assert invalid_provider.status_code == 422


def test_article_feedback_roundtrip(client, auth_headers):
    digest_id, article_ids = _create_digest_with_articles(article_count=1)
    article_id = article_ids[0]

    create = client.post(
        f"/api/articles/{article_id}/feedback",
        json={
            "rating": "up",
            "read_duration_sec": 42,
            "bookmarked": True,
            "shared": False,
        },
        headers=auth_headers,
    )
    assert create.status_code == 200
    payload = create.json()
    assert payload["article_id"] == str(article_id)
    assert payload["digest_id"] == str(digest_id)
    assert payload["rating"] == "up"
    assert payload["bookmarked"] is True

    delete = client.delete(f"/api/articles/{article_id}/feedback", headers=auth_headers)
    assert delete.status_code == 204

    missing = client.delete(f"/api/articles/{article_id}/feedback", headers=auth_headers)
    assert missing.status_code == 404


def test_trigger_digest_podcast_and_list_episodes(client, monkeypatch, auth_headers):
    monkeypatch.setattr(podcast_service, "_schedule_episode_task", lambda _episode_id: None)
    digest_id, _ = _create_digest_with_articles(article_count=2)

    trigger = client.post(f"/api/digests/{digest_id}/podcast", headers=auth_headers)
    assert trigger.status_code == 200
    trigger_payload = trigger.json()
    assert trigger_payload["status"] == "pending"
    episode_id = trigger_payload["episode_id"]

    status_resp = client.get(f"/api/digests/{digest_id}/podcast", headers=auth_headers)
    assert status_resp.status_code == 200
    assert status_resp.json()["episode"]["id"] == episode_id

    list_resp = client.get("/api/podcast/episodes", headers=auth_headers)
    assert list_resp.status_code == 200
    ids = {item["id"] for item in list_resp.json()}
    assert episode_id in ids


def test_retry_failed_podcast_episode(client, monkeypatch, auth_headers):
    monkeypatch.setattr(podcast_service, "_schedule_episode_task", lambda _episode_id: None)
    digest_id, article_ids = _create_digest_with_articles(article_count=2)
    failed = _create_episode(
        digest_id=digest_id,
        article_ids=article_ids,
        status="failed",
    )

    retry = client.post(f"/api/podcast/episodes/{failed.id}/retry", headers=auth_headers)
    assert retry.status_code == 200
    payload = retry.json()
    assert payload["episode_id"] == str(failed.id)
    assert payload["status"] == "pending"

    with Session(engine) as session:
        refreshed = session.get(PodcastEpisode, failed.id)
        assert refreshed is not None
        assert refreshed.status == "pending"


def test_trigger_digest_podcast_requeues_failed_episode(client, monkeypatch, auth_headers):
    scheduled: list[UUID] = []
    monkeypatch.setattr(
        podcast_service,
        "_schedule_episode_task",
        lambda episode_id: scheduled.append(episode_id),
    )
    digest_id, article_ids = _create_digest_with_articles(article_count=2)
    failed = _create_episode(
        digest_id=digest_id,
        article_ids=article_ids,
        status="failed",
    )

    trigger = client.post(f"/api/digests/{digest_id}/podcast", headers=auth_headers)
    assert trigger.status_code == 200
    payload = trigger.json()
    assert payload["episode_id"] == str(failed.id)
    assert payload["status"] == "pending"

    with Session(engine) as session:
        refreshed = session.get(PodcastEpisode, failed.id)
        assert refreshed is not None
        assert refreshed.status == "pending"
        assert refreshed.error_message is None
        assert refreshed.started_at is None
        assert refreshed.completed_at is None

    assert scheduled == [failed.id]


@pytest.mark.asyncio
async def test_run_episode_generation_uses_runtime_preference_snapshot(monkeypatch):
    monkeypatch.setattr(podcast_service, "_schedule_episode_task", lambda _episode_id: None)
    digest_id, _ = _create_digest_with_articles(article_count=2)

    with Session(engine) as session:
        prefs = podcast_service.get_or_create_preferences(session, user_id=None)
        prefs.openai_api_key = "test-openai-key"
        session.add(prefs)
        session.commit()
        episode = podcast_service.queue_episode_generation(session, digest_id=digest_id)
        episode_id = episode.id

    async def _fake_generate_script(_articles, prefs):
        assert isinstance(prefs, PodcastGenerationPreferences)
        return (
            "[HOST_A]: Intro\n"
            "[HOST_B]: Context\n"
            "[HOST_A]: Story one\n"
            "[HOST_B]: Story one context\n"
            "[HOST_A]: Story two\n"
            "[HOST_B]: Closing\n"
        )

    async def _fake_generate_audio(_episode_id, _segments, prefs):
        assert isinstance(prefs, PodcastGenerationPreferences)
        return AudioGenerationResult(
            audio_path="/tmp/podcast-test.mp3",
            audio_size_bytes=1234,
            duration_seconds=42,
            synthesized_chars=250,
        )

    monkeypatch.setattr(podcast_service, "generate_script", _fake_generate_script)
    monkeypatch.setattr(podcast_service, "generate_audio", _fake_generate_audio)

    await podcast_service._run_episode_generation(episode_id)

    with Session(engine) as session:
        refreshed = session.get(PodcastEpisode, episode_id)
        assert refreshed is not None
        assert refreshed.status == "ready"
        assert refreshed.error_message is None


def test_stream_download_and_feed_with_token_auth(client, tmp_path):
    digest_id, article_ids = _create_digest_with_articles(article_count=2)
    audio_path = tmp_path / "episode.mp3"
    audio_path.write_bytes(b"0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    episode = _create_episode(
        digest_id=digest_id,
        article_ids=article_ids,
        status="ready",
        audio_path=audio_path,
    )

    with Session(engine) as session:
        prefs = podcast_service.get_or_create_preferences(session, user_id=None)
        prefs.enabled = True
        prefs.podcast_feed_enabled = True
        prefs.podcast_feed_title = "Feed Title"
        prefs.podcast_feed_description = "Feed Description"
        prefs.podcast_feed_token = "feed_token_123456"
        prefs.updated_at = datetime.utcnow()
        session.add(prefs)
        session.commit()

    stream = client.get(
        f"/api/podcast/episodes/{episode.id}/stream?token=feed_token_123456",
        headers={"Range": "bytes=0-9"},
    )
    assert stream.status_code == 206
    assert stream.content == b"0123456789"
    assert stream.headers["content-range"].startswith("bytes 0-9/")

    download = client.get(f"/api/podcast/episodes/{episode.id}/download?token=feed_token_123456")
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("audio/mpeg")
    assert download.content == audio_path.read_bytes()

    feed = client.get("/api/podcast/feed.xml?token=feed_token_123456")
    assert feed.status_code == 200
    assert "application/rss+xml" in feed.headers["content-type"]
    root = ET.fromstring(feed.content)
    items = root.findall("./channel/item")
    assert items
    enclosure = items[0].find("enclosure")
    assert enclosure is not None
    assert str(episode.id) in enclosure.attrib["url"]
    assert "token=feed_token_123456" in enclosure.attrib["url"]


def test_feed_artwork_upload_and_serve(client, auth_headers):
    image = Image.new("RGB", (1500, 1500), color=(10, 20, 30))
    buffer = BytesIO()
    image.save(buffer, format="JPEG")
    buffer.seek(0)

    upload = client.post(
        "/api/podcast/feed/artwork",
        files={"file": ("artwork.jpg", buffer.getvalue(), "image/jpeg")},
        headers=auth_headers,
    )
    assert upload.status_code == 200
    upload_payload = upload.json()
    assert upload_payload["status"] == "uploaded"
    assert upload_payload["width"] == 1500
    assert upload_payload["height"] == 1500

    with Session(engine) as session:
        prefs = podcast_service.get_or_create_preferences(session, user_id=None)
        prefs.podcast_feed_enabled = True
        prefs.updated_at = datetime.utcnow()
        token = prefs.podcast_feed_token
        session.add(prefs)
        session.commit()

    artwork = client.get(f"/api/podcast/feed/artwork?token={token}")
    assert artwork.status_code == 200
    assert artwork.headers["content-type"].startswith("image/")

    info = client.get("/api/podcast/feed/info", headers=auth_headers)
    assert info.status_code == 200
    info_payload = info.json()
    assert "feed.xml?token=" in info_payload["feed_url"]


def test_auto_generation_schedule_trigger(monkeypatch):
    monkeypatch.setattr(podcast_service, "_schedule_episode_task", lambda _episode_id: None)
    completed_at = datetime(2099, 1, 10, 12, 0, 0)
    digest_id, _ = _create_digest_with_articles(article_count=2, completed_at=completed_at)

    with Session(engine) as session:
        prefs = podcast_service.get_or_create_preferences(session, user_id=None)
        prefs.enabled = True
        prefs.schedule = "daily"
        prefs.schedule_time = "00:00"
        prefs.updated_at = datetime.utcnow()
        session.add(prefs)
        session.commit()

    episode_id = podcast_service.maybe_auto_generate_for_digest(digest_id)
    assert episode_id is not None

    with Session(engine) as session:
        episode = session.get(PodcastEpisode, UUID(str(episode_id)))
        assert episode is not None
        assert episode.digest_id == digest_id
        assert episode.status == "pending"
