"""Tests for podcast digest APIs and scheduling behavior."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from PIL import Image
from sqlmodel import Session, select

from app.core.auth import generate_api_token, get_token_prefix, hash_api_token
from app.core.config import get_settings
from app.core.database import engine
from app.models.api_token import APIToken
from app.models.digest import Digest, DigestArticle
from app.models.feed import Feed
from app.models.podcast_episode import PodcastEpisode
from app.models.podcast_preferences import PodcastPreferences
from app.models.podcast_schedule import PodcastSchedule
from app.models.user import User
from app.services.one_off_podcast_service import (
    ONE_OFF_MAX_BRIEF_CHARS,
    ONE_OFF_MAX_TEXT_CHARS,
    ONE_OFF_SOURCE_LABEL,
)
from app.services.podcast_service import (
    AudioGenerationResult,
    PodcastGenerationPreferences,
    podcast_service,
)
from app.services.reader_service import FetchedHtmlDocument


def _create_digest_with_articles(
    *,
    article_count: int = 3,
    completed_at: datetime | None = None,
    feed_url: str | None = None,
    feed_title: str | None = None,
) -> tuple[UUID, list[UUID]]:
    suffix = str(uuid4())[:8]
    created = completed_at or datetime.utcnow()
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
        feed = None
        if feed_url is not None:
            feed = session.exec(select(Feed).where(Feed.url == feed_url)).first()
        if feed is None:
            feed = Feed(
                url=feed_url or f"https://example.com/feed/{suffix}.xml",
                title=feed_title or f"Feed {suffix}",
                is_active=True,
                mode="raw",
                max_articles=5,
            )
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
    trigger: str = "manual",
    user_id: UUID | None = None,
) -> PodcastEpisode:
    now = datetime.utcnow()
    episode = PodcastEpisode(
        digest_ids=[str(digest_id)],
        trigger=trigger,
        user_id=user_id,
        script="[HOST_A]: Intro\n[HOST_B]: Reply\n[HOST_A]: Outro\n[HOST_B]: End\n"
        "[HOST_A]: Next\n[HOST_B]: Done",
        audio_path=str(audio_path) if audio_path else None,
        audio_size_bytes=audio_path.stat().st_size
        if audio_path and audio_path.exists()
        else None,
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


def _test_podcast_preferences(**overrides) -> PodcastGenerationPreferences:
    values = {
        "topic_weights": {"general": 1.0},
        "boost_sources": [],
        "boost_keywords": [],
        "filter_keywords": [],
        "preferred_length_minutes": 15,
        "script_model": None,
        "script_timeout_seconds": 60,
        "style": "casual",
        "tts_provider": "openai",
        "openai_tts_model": "tts-1",
        "openai_api_key": None,
        "elevenlabs_model_id": "eleven_turbo_v2_5",
        "elevenlabs_api_key": None,
        "elevenlabs_output_format": "mp3_44100_128",
        "host_a_voice": "alloy",
        "host_b_voice": "echo",
        "host_count": 2,
    }
    values.update(overrides)
    return PodcastGenerationPreferences(**values)


def _podcast_test_article(
    *,
    title: str,
    content: str,
    feed_title: str = "Source",
    word_count: int | None = None,
    sort_order: int = 0,
) -> DigestArticle:
    return DigestArticle(
        digest_id=uuid4(),
        feed_id=uuid4(),
        title=title,
        url=f"https://example.com/{uuid4()}",
        mode="raw",
        word_count=word_count if word_count is not None else len(content.split()),
        ai_failed=False,
        processing_ms=10,
        content=content,
        author="Reporter",
        feed_title=feed_title,
        sort_order=sort_order,
        content_type="article",
    )


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Create an API token and return auth headers for protected endpoints."""
    with Session(engine) as session:
        user = session.exec(select(User).order_by(User.created_at.asc())).first()
        if user is None:
            user = User(
                username=f"podcast_user_{str(uuid4())[:8]}",
                password_hash="test-hash",
                is_admin=True,
            )
            session.add(user)
            session.commit()
            session.refresh(user)

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


def _create_auth_headers_for_user(username: str) -> tuple[UUID, dict[str, str]]:
    raw_token = generate_api_token()
    with Session(engine) as session:
        user = User(
            username=f"{username}_{str(uuid4())[:8]}",
            password_hash="test-hash",
            is_admin=False,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        token_row = APIToken(
            user_id=user.id,
            name=f"podcast-test-{str(uuid4())[:8]}",
            token_hash=hash_api_token(raw_token),
            token_prefix=get_token_prefix(raw_token),
        )
        session.add(token_row)
        session.commit()
        user_id = user.id

    return user_id, {"X-API-Key": raw_token}


def test_podcast_preferences_get_and_update(client, auth_headers):
    response = client.get("/api/podcast/preferences", headers=auth_headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["enabled"] is False
    assert payload["schedule"] == "manual"
    assert payload["preferred_length_minutes"] == 15
    assert payload["script_model"] is None
    assert payload["script_timeout_seconds"] == 60
    assert payload["tts_provider"] == "openai"
    assert payload["openai_tts_model"] == "tts-1"
    assert payload["podcast_feed_base_url"] is None

    update = client.put(
        "/api/podcast/preferences",
        json={
            "enabled": True,
            "schedule": "weekly",
            "schedule_time": "09:30",
            "schedule_day": "friday",
            "style": "formal",
            "script_model": "gpt-4.1-mini",
            "script_timeout_seconds": 180,
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
            "podcast_feed_base_url": "https://podcasts.example.com",
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
    assert updated["script_model"] == "gpt-4.1-mini"
    assert updated["script_timeout_seconds"] == 180
    assert updated["tts_provider"] == "elevenlabs"
    assert updated["elevenlabs_model_id"] == "eleven_flash_v2_5"
    assert updated["elevenlabs_output_format"] == "mp3_44100_128"
    assert updated["boost_keywords"] == ["AI", "Swift"]
    assert updated["podcast_feed_enabled"] is True
    assert updated["podcast_feed_title"] == "My Test Feed"
    assert updated["podcast_feed_base_url"] == "https://podcasts.example.com"

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

    invalid_feed_base_url = client.put(
        "/api/podcast/preferences",
        json={"podcast_feed_base_url": "not-a-url"},
        headers=auth_headers,
    )
    assert invalid_feed_base_url.status_code == 400
    assert "podcast_feed_base_url" in invalid_feed_base_url.json()["detail"]


def test_podcast_preferences_are_scoped_to_token_owner(client):
    owner_id, _owner_headers = _create_auth_headers_for_user("prefs_owner")
    user_id, headers = _create_auth_headers_for_user("prefs_secondary")

    with Session(engine) as session:
        owner_prefs = podcast_service.get_or_create_preferences(
            session,
            user_id=owner_id,
        )
        owner_prefs.podcast_feed_enabled = True
        owner_prefs.podcast_feed_token = "feed_token_prefs_owner"
        owner_prefs.podcast_feed_title = "Owner Feed"
        session.add(owner_prefs)
        session.commit()

    update = client.put(
        "/api/podcast/preferences",
        json={
            "podcast_feed_enabled": True,
            "podcast_feed_title": "Secondary Feed",
            "preferred_length_minutes": 25,
        },
        headers=headers,
    )
    assert update.status_code == 200
    assert update.json()["podcast_feed_enabled"] is True
    assert update.json()["podcast_feed_title"] == "Secondary Feed"
    assert update.json()["preferred_length_minutes"] == 25

    info = client.get("/api/podcast/feed/info", headers=headers)
    assert info.status_code == 200
    info_payload = info.json()
    assert info_payload["feed_enabled"] is True
    assert info_payload["feed_title"] == "Secondary Feed"
    assert "feed_token_prefs_owner" not in info_payload["feed_url"]

    schedule_update = client.put(
        "/api/podcast/preferences",
        json={"enabled": True, "schedule": "daily"},
        headers=headers,
    )
    assert schedule_update.status_code == 400
    assert "schedule settings" in schedule_update.json()["detail"]

    with Session(engine) as session:
        owner_prefs = session.exec(
            select(PodcastPreferences).where(PodcastPreferences.user_id == owner_id)
        ).first()
        prefs = session.exec(
            select(PodcastPreferences).where(PodcastPreferences.user_id == user_id)
        ).one()

    assert owner_prefs is not None
    assert owner_prefs.podcast_feed_title == "Owner Feed"
    assert prefs.podcast_feed_title == "Secondary Feed"
    assert prefs.podcast_feed_token in info_payload["feed_url"]


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

    missing = client.delete(
        f"/api/articles/{article_id}/feedback", headers=auth_headers
    )
    assert missing.status_code == 404


def test_trigger_digest_podcast_and_list_episodes(client, monkeypatch, auth_headers):
    monkeypatch.setattr(
        podcast_service, "_schedule_episode_task", lambda _episode_id: None
    )
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


def test_trigger_digest_podcast_uses_authenticated_token_owner(client, monkeypatch):
    monkeypatch.setattr(
        podcast_service, "_schedule_episode_task", lambda _episode_id: None
    )
    owner_id, owner_headers = _create_auth_headers_for_user("manual_podcast_owner")
    user_id, headers = _create_auth_headers_for_user("manual_podcast_secondary")
    digest_id, _ = _create_digest_with_articles(article_count=2)

    owner_trigger = client.post(
        f"/api/digests/{digest_id}/podcast",
        headers=owner_headers,
    )
    assert owner_trigger.status_code == 200
    owner_episode_id = UUID(owner_trigger.json()["episode_id"])

    trigger = client.post(f"/api/digests/{digest_id}/podcast", headers=headers)
    assert trigger.status_code == 200
    episode_id = UUID(trigger.json()["episode_id"])
    assert episode_id != owner_episode_id

    with Session(engine) as session:
        owner_episode = session.get(PodcastEpisode, owner_episode_id)
        episode = session.get(PodcastEpisode, episode_id)

    assert owner_episode is not None
    assert owner_episode.user_id == owner_id
    assert episode is not None
    assert episode.user_id == user_id

    owner_detail = client.get(
        f"/api/podcast/episodes/{owner_episode_id}",
        headers=headers,
    )
    assert owner_detail.status_code == 404

    digest_status = client.get(f"/api/digests/{digest_id}/podcast", headers=headers)
    assert digest_status.status_code == 200
    assert digest_status.json()["episode"]["id"] == str(episode_id)

    list_response = client.get("/api/podcast/episodes", headers=headers)
    assert list_response.status_code == 200
    listed_ids = {item["id"] for item in list_response.json()}
    assert str(episode_id) in listed_ids
    assert str(owner_episode_id) not in listed_ids


def test_create_one_off_podcast_from_text_sources(client, monkeypatch, auth_headers):
    monkeypatch.setattr(
        podcast_service, "_schedule_episode_task", lambda _episode_id: None
    )

    response = client.post(
        "/api/podcast/episodes/one-off",
        json={
            "title": "OpenClaw planning brief",
            "brief": "Focus on implementation tradeoffs.",
            "sources": [
                {
                    "type": "text",
                    "title": "OpenClaw notes",
                    "content": (
                        "OpenClaw should generate one-off podcast episodes from "
                        "selected documents. The implementation should reuse the "
                        "existing digest-backed podcast pipeline and preserve the "
                        "submitted source order."
                    ),
                },
                {
                    "type": "text",
                    "title": "Hermes notes",
                    "content": (
                        "Hermes needs an assistant-friendly endpoint that accepts "
                        "documents, creates a manual digest, and queues audio "
                        "generation without requiring a scheduled digest run."
                    ),
                },
            ],
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "pending"
    assert payload["message"] == "One-off podcast generation queued"
    assert len(payload["digest_ids"]) == 1

    episode_id = UUID(payload["episode_id"])
    digest_id = UUID(payload["digest_ids"][0])
    with Session(engine) as session:
        episode = session.get(PodcastEpisode, episode_id)
        digest = session.get(Digest, digest_id)
        articles = session.exec(
            select(DigestArticle)
            .where(DigestArticle.digest_id == digest_id)
            .order_by(DigestArticle.sort_order.asc())
        ).all()
        first_article_id = articles[0].id
        feed = session.exec(select(Feed).where(Feed.url == "synthetic://one-off")).first()

    assert episode is not None
    assert episode.trigger == "one_off"
    assert str(digest_id) in (episode.digest_ids or [])
    assert digest is not None
    assert digest.status == "completed"
    assert digest.period == "manual"
    assert digest.article_count == 2
    assert (Path(get_settings().output_dir) / digest.filename).exists()
    assert feed is not None
    assert feed.title == ONE_OFF_SOURCE_LABEL
    assert [article.title for article in articles] == ["OpenClaw notes", "Hermes notes"]
    assert [article.sort_order for article in articles] == [0, 1]
    assert all(article.feed_title == ONE_OFF_SOURCE_LABEL for article in articles)
    assert "Episode title: OpenClaw planning brief" in articles[0].content
    assert "Caller brief: Focus on implementation tradeoffs." in articles[0].content

    download = client.get(
        f"/api/digests/{digest_id}/download?format=epub",
        headers=auth_headers,
    )
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("application/epub+zip")

    source = client.get(
        f"/api/digests/{digest_id}/articles/{articles[0].id}/source",
        headers=auth_headers,
    )
    assert source.status_code == 200
    assert source.json()["content_type"] == "text/html; ghostwriter-one-off"
    assert "selected documents" in source.json()["html"]


def test_one_off_episode_trigger_is_persisted_before_scheduling(
    client, monkeypatch, auth_headers
):
    scheduled_triggers: list[str | None] = []

    def capture_scheduled_trigger(episode_id: UUID) -> None:
        with Session(engine) as session:
            episode = session.get(PodcastEpisode, episode_id)
            scheduled_triggers.append(episode.trigger if episode else None)

    monkeypatch.setattr(
        podcast_service, "_schedule_episode_task", capture_scheduled_trigger
    )

    response = client.post(
        "/api/podcast/episodes/one-off",
        json={
            "title": "Pre-schedule trigger check",
            "sources": [
                {
                    "type": "text",
                    "title": "Trigger notes",
                    "content": (
                        "This source is long enough to become a one-off podcast "
                        "digest article, and the worker must see the one-off trigger "
                        "before any asynchronous generation task can begin."
                    ),
                }
            ],
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert scheduled_triggers == ["one_off"]


def test_one_off_digest_is_not_committed_before_article_markers(
    client, monkeypatch, auth_headers
):
    from app.services.one_off_podcast_service import OneOffPodcastError

    monkeypatch.setattr(
        podcast_service, "_schedule_episode_task", lambda _episode_id: None
    )

    def _raise_before_digest_marker_commit(*_args, **_kwargs):
        raise OneOffPodcastError("synthetic feed unavailable")

    monkeypatch.setattr(
        "app.services.one_off_podcast_service.get_or_create_synthetic_feed",
        _raise_before_digest_marker_commit,
    )
    with Session(engine) as session:
        digest_count_before = len(session.exec(select(Digest)).all())

    response = client.post(
        "/api/podcast/episodes/one-off",
        json={
            "sources": [
                {
                    "type": "text",
                    "title": "Uncommitted private source",
                    "content": (
                        "This private source is long enough to be accepted but "
                        "synthetic feed setup fails before the digest should be "
                        "visible to normal digest list or sync responses."
                    ),
                }
            ],
        },
        headers=auth_headers,
    )

    assert response.status_code == 409
    assert "synthetic feed unavailable" in response.json()["detail"]
    with Session(engine) as session:
        digest_count_after = len(session.exec(select(Digest)).all())

    assert digest_count_after == digest_count_before


def test_failed_one_off_epub_generation_removes_private_digest(
    client, monkeypatch, auth_headers
):
    class FailingEpubGenerator:
        def __init__(self, *_args, **_kwargs):
            pass

        def generate(self, *_args, **_kwargs):
            raise RuntimeError("epub unavailable")

    monkeypatch.setattr(
        podcast_service, "_schedule_episode_task", lambda _episode_id: None
    )
    monkeypatch.setattr(
        "app.services.one_off_podcast_service.EpubGenerator",
        FailingEpubGenerator,
    )
    with Session(engine) as session:
        digest_count_before = len(session.exec(select(Digest)).all())
        article_count_before = len(session.exec(select(DigestArticle)).all())

    response = client.post(
        "/api/podcast/episodes/one-off",
        json={
            "sources": [
                {
                    "type": "text",
                    "title": "Failed EPUB private source",
                    "content": (
                        "This private source is long enough to create one-off "
                        "article markers, but EPUB generation fails before an "
                        "owning podcast episode can be created."
                    ),
                }
            ],
        },
        headers=auth_headers,
    )

    assert response.status_code == 409
    assert "epub unavailable" in response.json()["detail"]
    with Session(engine) as session:
        digest_count_after = len(session.exec(select(Digest)).all())
        article_count_after = len(session.exec(select(DigestArticle)).all())

    assert digest_count_after == digest_count_before
    assert article_count_after == article_count_before


def test_one_off_digest_access_requires_episode_owner(client, monkeypatch):
    monkeypatch.setattr(
        podcast_service, "_schedule_episode_task", lambda _episode_id: None
    )
    _owner_id, owner_headers = _create_auth_headers_for_user("oneoff_owner")
    _other_id, other_headers = _create_auth_headers_for_user("oneoff_other")

    response = client.post(
        "/api/podcast/episodes/one-off",
        json={
            "title": "Private owner brief",
            "sources": [
                {
                    "type": "text",
                    "title": "Private source notes",
                    "content": (
                        "These private source notes should be available to the "
                        "one-off episode owner, but they must not be readable via "
                        "digest article or EPUB endpoints by another token owner."
                    ),
                }
            ],
        },
        headers=owner_headers,
    )

    assert response.status_code == 200
    digest_id = response.json()["digest_ids"][0]
    with Session(engine) as session:
        digest = session.get(Digest, UUID(digest_id))
        assert digest is not None
        filename = digest.filename

    list_response = client.get("/api/digests", headers=owner_headers)
    assert list_response.status_code == 200
    assert digest_id not in {item["id"] for item in list_response.json()}

    sync_response = client.get("/api/sync", headers=owner_headers)
    assert sync_response.status_code == 200
    sync_digests = sync_response.json()["digests"]["new_digests"]
    assert digest_id not in {item["id"] for item in sync_digests}

    owner_articles = client.get(
        f"/api/digests/{digest_id}/articles",
        headers=owner_headers,
    )
    assert owner_articles.status_code == 200
    article_id = owner_articles.json()["articles"][0]["id"]

    other_articles = client.get(
        f"/api/digests/{digest_id}/articles",
        headers=other_headers,
    )
    assert other_articles.status_code == 404

    other_source = client.get(
        f"/api/digests/{digest_id}/articles/{article_id}/source",
        headers=other_headers,
    )
    assert other_source.status_code == 404

    owner_download = client.get(
        f"/api/digests/{digest_id}/download",
        headers=owner_headers,
    )
    assert owner_download.status_code == 200

    other_download = client.get(
        f"/api/digests/{digest_id}/download",
        headers=other_headers,
    )
    assert other_download.status_code == 404

    owner_filename_download = client.get(
        f"/api/digests/{filename}",
        headers=owner_headers,
    )
    assert owner_filename_download.status_code == 200

    other_filename_download = client.get(
        f"/api/digests/{filename}",
        headers=other_headers,
    )
    assert other_filename_download.status_code == 404

    other_filename_delete = client.delete(
        f"/api/digests/{filename}",
        headers=other_headers,
    )
    assert other_filename_delete.status_code == 404

    owner_podcast_status = client.get(
        f"/api/digests/{digest_id}/podcast",
        headers=owner_headers,
    )
    assert owner_podcast_status.status_code == 200

    other_podcast_status = client.get(
        f"/api/digests/{digest_id}/podcast",
        headers=other_headers,
    )
    assert other_podcast_status.status_code == 404

    other_podcast_trigger = client.post(
        f"/api/digests/{digest_id}/podcast",
        headers=other_headers,
    )
    assert other_podcast_trigger.status_code == 404


def test_orphaned_one_off_digest_fails_closed(client, monkeypatch):
    monkeypatch.setattr(
        podcast_service, "_schedule_episode_task", lambda _episode_id: None
    )
    _owner_id, owner_headers = _create_auth_headers_for_user("orphan_owner")

    response = client.post(
        "/api/podcast/episodes/one-off",
        json={
            "title": "Orphaned private digest",
            "sources": [
                {
                    "type": "text",
                    "title": "Private orphan source",
                    "content": (
                        "This source creates a one-off digest whose podcast episode "
                        "will be deleted to verify that digest access fails closed."
                    ),
                }
            ],
        },
        headers=owner_headers,
    )
    assert response.status_code == 200
    payload = response.json()
    digest_id = payload["digest_ids"][0]
    episode_id = UUID(payload["episode_id"])

    with Session(engine) as session:
        episode = session.get(PodcastEpisode, episode_id)
        assert episode is not None
        session.delete(episode)
        session.commit()

    articles = client.get(
        f"/api/digests/{digest_id}/articles",
        headers=owner_headers,
    )
    assert articles.status_code == 404

    download = client.get(
        f"/api/digests/{digest_id}/download",
        headers=owner_headers,
    )
    assert download.status_code == 404


def test_one_off_episode_access_requires_episode_owner(client, monkeypatch):
    monkeypatch.setattr(
        podcast_service, "_schedule_episode_task", lambda _episode_id: None
    )
    owner_id, owner_headers = _create_auth_headers_for_user("episode_owner")
    _other_id, other_headers = _create_auth_headers_for_user("episode_other")

    digest_id, article_ids = _create_digest_with_articles(
        article_count=2,
        feed_url="synthetic://one-off",
        feed_title=ONE_OFF_SOURCE_LABEL,
    )
    settings = get_settings()
    podcasts_dir = Path(settings.output_dir) / "podcasts"
    podcasts_dir.mkdir(parents=True, exist_ok=True)
    audio_path = podcasts_dir / f"one-off-private-{uuid4()}.mp3"
    audio_path.write_bytes(b"private one-off audio")

    ready_episode = _create_episode(
        digest_id=digest_id,
        article_ids=article_ids,
        status="ready",
        audio_path=audio_path,
        trigger="one_off",
        user_id=owner_id,
    )
    failed_episode = _create_episode(
        digest_id=digest_id,
        article_ids=article_ids,
        status="failed",
        trigger="one_off",
        user_id=owner_id,
    )

    owner_list = client.get("/api/podcast/episodes", headers=owner_headers)
    assert owner_list.status_code == 200
    assert str(ready_episode.id) in {item["id"] for item in owner_list.json()}

    other_list = client.get("/api/podcast/episodes", headers=other_headers)
    assert other_list.status_code == 200
    assert str(ready_episode.id) not in {item["id"] for item in other_list.json()}

    owner_detail = client.get(
        f"/api/podcast/episodes/{ready_episode.id}",
        headers=owner_headers,
    )
    assert owner_detail.status_code == 200

    other_detail = client.get(
        f"/api/podcast/episodes/{ready_episode.id}",
        headers=other_headers,
    )
    assert other_detail.status_code == 404

    owner_stream = client.get(
        f"/api/podcast/episodes/{ready_episode.id}/stream",
        headers=owner_headers,
    )
    assert owner_stream.status_code == 200

    other_stream = client.get(
        f"/api/podcast/episodes/{ready_episode.id}/stream",
        headers=other_headers,
    )
    assert other_stream.status_code == 404

    owner_download = client.get(
        f"/api/podcast/episodes/{ready_episode.id}/download",
        headers=owner_headers,
    )
    assert owner_download.status_code == 200

    other_download = client.get(
        f"/api/podcast/episodes/{ready_episode.id}/download",
        headers=other_headers,
    )
    assert other_download.status_code == 404

    other_retry = client.post(
        f"/api/podcast/episodes/{failed_episode.id}/retry",
        headers=other_headers,
    )
    assert other_retry.status_code == 404

    other_delete = client.delete(
        f"/api/podcast/episodes/{ready_episode.id}",
        headers=other_headers,
    )
    assert other_delete.status_code == 404


def test_one_off_podcast_uses_unique_digest_filenames(
    client, monkeypatch, auth_headers
):
    monkeypatch.setattr(
        podcast_service, "_schedule_episode_task", lambda _episode_id: None
    )
    request = {
        "title": "OpenClaw planning brief",
        "sources": [
            {
                "type": "text",
                "title": "OpenClaw notes",
                "content": (
                    "OpenClaw should generate one-off podcast episodes from "
                    "selected documents while preserving the submitted source order."
                ),
            }
        ],
    }

    first = client.post(
        "/api/podcast/episodes/one-off",
        json=request,
        headers=auth_headers,
    )
    second = client.post(
        "/api/podcast/episodes/one-off",
        json=request,
        headers=auth_headers,
    )

    assert first.status_code == 200
    assert second.status_code == 200
    digest_ids = [
        UUID(first.json()["digest_ids"][0]),
        UUID(second.json()["digest_ids"][0]),
    ]
    with Session(engine) as session:
        digests = [session.get(Digest, digest_id) for digest_id in digest_ids]

    filenames = [digest.filename for digest in digests if digest is not None]
    assert len(filenames) == 2
    assert filenames[0] != filenames[1]
    assert all((Path(get_settings().output_dir) / filename).exists() for filename in filenames)


def test_create_one_off_podcast_uses_authenticated_token_owner(client, monkeypatch):
    monkeypatch.setattr(
        podcast_service, "_schedule_episode_task", lambda _episode_id: None
    )
    with Session(engine) as session:
        user_a = User(
            username=f"podcast_owner_a_{str(uuid4())[:8]}",
            password_hash="test-hash",
            is_admin=False,
        )
        user_b = User(
            username=f"podcast_owner_b_{str(uuid4())[:8]}",
            password_hash="test-hash",
            is_admin=False,
        )
        session.add(user_a)
        session.add(user_b)
        session.commit()
        session.refresh(user_a)
        session.refresh(user_b)

        raw_token = generate_api_token()
        token_row = APIToken(
            user_id=user_b.id,
            name=f"podcast-test-{str(uuid4())[:8]}",
            token_hash=hash_api_token(raw_token),
            token_prefix=get_token_prefix(raw_token),
        )
        session.add(token_row)
        session.commit()
        user_b_id = user_b.id

    response = client.post(
        "/api/podcast/episodes/one-off",
        json={
            "title": "Private OpenClaw brief",
            "sources": [
                {
                    "type": "text",
                    "title": "Private notes",
                    "content": (
                        "This private OpenClaw source material should be assigned "
                        "to the authenticated API token owner, not the first user."
                    ),
                }
            ],
        },
        headers={"X-API-Key": raw_token},
    )

    assert response.status_code == 200
    episode_id = UUID(response.json()["episode_id"])
    with Session(engine) as session:
        episode = session.get(PodcastEpisode, episode_id)

    assert episode is not None
    assert episode.user_id == user_b_id


def test_create_one_off_podcast_rejects_overlong_brief(client, auth_headers):
    response = client.post(
        "/api/podcast/episodes/one-off",
        json={
            "title": "OpenClaw planning brief",
            "brief": "x" * (ONE_OFF_MAX_BRIEF_CHARS + 1),
            "sources": [
                {
                    "type": "text",
                    "title": "OpenClaw notes",
                    "content": (
                        "OpenClaw should generate one-off podcast episodes from "
                        "selected documents while preserving the submitted source order."
                    ),
                }
            ],
        },
        headers=auth_headers,
    )

    assert response.status_code == 422


def test_create_one_off_podcast_rejects_combined_source_over_limit(
    client,
    monkeypatch,
    auth_headers,
):
    monkeypatch.setattr(
        podcast_service, "_schedule_episode_task", lambda _episode_id: None
    )

    response = client.post(
        "/api/podcast/episodes/one-off",
        json={
            "brief": "This brief pushes the prepared article over the size limit.",
            "sources": [
                {
                    "type": "text",
                    "title": "Large OpenClaw notes",
                    "content": "a" * (ONE_OFF_MAX_TEXT_CHARS - 10),
                }
            ],
        },
        headers=auth_headers,
    )

    assert response.status_code == 409
    assert "Combined one-off source content exceeds" in response.json()["detail"]


def test_create_one_off_podcast_from_url_source(client, monkeypatch, auth_headers):
    monkeypatch.setattr(
        podcast_service, "_schedule_episode_task", lambda _episode_id: None
    )

    async def _fetch_html_document(url: str, **_kwargs) -> FetchedHtmlDocument:
        assert url == "https://example.com/openclaw-roadmap"
        html = """
        <html>
          <head><title>OpenClaw roadmap</title></head>
          <body>
            <article>
              <p>The roadmap explains how OpenClaw can package selected research
              documents into a podcast episode.</p>
              <p>It highlights source mapping, script generation, TTS reuse, and
              feed publication.</p>
            </article>
          </body>
        </html>
        """
        return FetchedHtmlDocument(
            url=url,
            final_url="https://example.com/openclaw-roadmap",
            content_type="text/html",
            html=html,
            fetched_at=datetime.utcnow(),
            size_bytes=len(html.encode("utf-8")),
        )

    monkeypatch.setattr(
        "app.services.one_off_podcast_service.fetch_html_document",
        _fetch_html_document,
    )

    response = client.post(
        "/api/podcast/episodes/one-off",
        json={
            "sources": [
                {
                    "type": "url",
                    "url": "https://example.com/openclaw-roadmap",
                }
            ],
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    digest_id = UUID(response.json()["digest_ids"][0])
    with Session(engine) as session:
        article = session.exec(
            select(DigestArticle).where(DigestArticle.digest_id == digest_id)
        ).one()

    assert article.url == "https://example.com/openclaw-roadmap"
    assert article.title == "openclaw roadmap"
    assert "source mapping" in article.content


def test_create_one_off_podcast_rejects_private_url_redirect(
    client,
    monkeypatch,
    auth_headers,
):
    monkeypatch.setattr(
        podcast_service, "_schedule_episode_task", lambda _episode_id: None
    )

    async def _fetch_html_document(_url: str, **_kwargs) -> FetchedHtmlDocument:
        raise ValueError("URL resolves to private address")

    monkeypatch.setattr(
        "app.services.one_off_podcast_service.fetch_html_document",
        _fetch_html_document,
    )

    response = client.post(
        "/api/podcast/episodes/one-off",
        json={
            "sources": [
                {
                    "type": "url",
                    "url": "https://example.com/private-redirect",
                }
            ],
        },
        headers=auth_headers,
    )

    assert response.status_code == 409
    assert "private address" in response.json()["detail"]


def test_create_one_off_podcast_rejects_unusable_sources(
    client, monkeypatch, auth_headers
):
    monkeypatch.setattr(
        podcast_service, "_schedule_episode_task", lambda _episode_id: None
    )

    response = client.post(
        "/api/podcast/episodes/one-off",
        json={
            "sources": [
                {
                    "type": "text",
                    "title": "Too short",
                    "content": "too short",
                }
            ],
        },
        headers=auth_headers,
    )

    assert response.status_code == 409
    assert "No usable sources" in response.json()["detail"]


def test_retry_failed_podcast_episode(client, monkeypatch, auth_headers):
    monkeypatch.setattr(
        podcast_service, "_schedule_episode_task", lambda _episode_id: None
    )
    digest_id, article_ids = _create_digest_with_articles(article_count=2)
    failed = _create_episode(
        digest_id=digest_id,
        article_ids=article_ids,
        status="failed",
    )

    retry = client.post(
        f"/api/podcast/episodes/{failed.id}/retry", headers=auth_headers
    )
    assert retry.status_code == 200
    payload = retry.json()
    assert payload["episode_id"] == str(failed.id)
    assert payload["status"] == "pending"

    with Session(engine) as session:
        refreshed = session.get(PodcastEpisode, failed.id)
        assert refreshed is not None
        assert refreshed.status == "pending"


def test_retry_failed_one_off_episode_preserves_trigger(client, monkeypatch):
    monkeypatch.setattr(
        podcast_service, "_schedule_episode_task", lambda _episode_id: None
    )
    owner_id, owner_headers = _create_auth_headers_for_user("retry_oneoff_owner")
    digest_id, article_ids = _create_digest_with_articles(
        article_count=2,
        feed_url="synthetic://one-off",
        feed_title=ONE_OFF_SOURCE_LABEL,
    )
    failed = _create_episode(
        digest_id=digest_id,
        article_ids=article_ids,
        status="failed",
        trigger="one_off",
        user_id=owner_id,
    )

    retry = client.post(
        f"/api/podcast/episodes/{failed.id}/retry", headers=owner_headers
    )
    assert retry.status_code == 200
    payload = retry.json()
    assert payload["episode_id"] == str(failed.id)
    assert payload["status"] == "pending"

    with Session(engine) as session:
        refreshed = session.get(PodcastEpisode, failed.id)
        assert refreshed is not None
        assert refreshed.status == "pending"
        assert refreshed.trigger == "one_off"


def test_trigger_digest_podcast_requeues_failed_episode(client, monkeypatch):
    scheduled: list[UUID] = []
    monkeypatch.setattr(
        podcast_service,
        "_schedule_episode_task",
        lambda episode_id: scheduled.append(episode_id),
    )
    user_id, headers = _create_auth_headers_for_user("manual_requeue_owner")
    digest_id, article_ids = _create_digest_with_articles(article_count=2)
    failed = _create_episode(
        digest_id=digest_id,
        article_ids=article_ids,
        status="failed",
        user_id=user_id,
    )

    trigger = client.post(f"/api/digests/{digest_id}/podcast", headers=headers)
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


def test_trigger_digest_podcast_preserves_existing_one_off_trigger(
    client, monkeypatch
):
    monkeypatch.setattr(
        podcast_service, "_schedule_episode_task", lambda _episode_id: None
    )
    owner_id, owner_headers = _create_auth_headers_for_user("trigger_oneoff_owner")
    digest_id, article_ids = _create_digest_with_articles(
        article_count=2,
        feed_url="synthetic://one-off",
        feed_title=ONE_OFF_SOURCE_LABEL,
    )
    failed = _create_episode(
        digest_id=digest_id,
        article_ids=article_ids,
        status="failed",
        trigger="one_off",
        user_id=owner_id,
    )

    trigger = client.post(f"/api/digests/{digest_id}/podcast", headers=owner_headers)
    assert trigger.status_code == 200

    with Session(engine) as session:
        refreshed = session.get(PodcastEpisode, failed.id)
        assert refreshed is not None
        assert refreshed.status == "pending"
        assert refreshed.trigger == "one_off"


@pytest.mark.asyncio
async def test_run_episode_generation_uses_runtime_preference_snapshot(monkeypatch):
    monkeypatch.setattr(
        podcast_service, "_schedule_episode_task", lambda _episode_id: None
    )
    digest_id, _ = _create_digest_with_articles(article_count=2)

    with Session(engine) as session:
        prefs = podcast_service.get_or_create_preferences(session, user_id=None)
        prefs.openai_api_key = "test-openai-key"
        session.add(prefs)
        session.commit()
        episode = podcast_service.queue_episode_generation(session, digest_id=digest_id)
        episode_id = episode.id

    async def _fake_generate_script(_articles, prefs, **_kwargs):
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
    settings = get_settings()
    podcasts_dir = Path(settings.output_dir) / "podcasts"
    podcasts_dir.mkdir(parents=True, exist_ok=True)
    audio_path = podcasts_dir / f"episode-{uuid4()}.mp3"
    audio_path.write_bytes(b"0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ")

    with Session(engine) as session:
        prefs = podcast_service.get_or_create_preferences(session, user_id=None)
        prefs.enabled = True
        prefs.podcast_feed_enabled = True
        prefs.podcast_feed_title = "Feed Title"
        prefs.podcast_feed_description = "Feed Description"
        prefs.podcast_feed_base_url = None
        prefs.podcast_feed_token = "feed_token_123456"
        prefs.updated_at = datetime.utcnow()
        user_id = prefs.user_id
        session.add(prefs)
        session.commit()

    episode = _create_episode(
        digest_id=digest_id,
        article_ids=article_ids,
        status="ready",
        audio_path=audio_path,
        user_id=user_id,
    )

    stream = client.get(
        f"/api/podcast/episodes/{episode.id}/stream?token=feed_token_123456",
        headers={"Range": "bytes=0-9"},
    )
    assert stream.status_code == 206
    assert stream.content == b"0123456789"
    assert stream.headers["content-range"].startswith("bytes 0-9/")

    download = client.get(
        f"/api/podcast/episodes/{episode.id}/download?token=feed_token_123456"
    )
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("audio/mpeg")
    assert download.content == audio_path.read_bytes()

    feed = client.get("/api/podcast/feed.xml?token=feed_token_123456")
    assert feed.status_code == 200
    assert "application/rss+xml" in feed.headers["content-type"]
    root = ET.fromstring(feed.content)
    channel = root.find("./channel")
    assert channel is not None
    assert channel.findtext("link") == "http://testserver"
    assert channel.findtext("lastBuildDate")
    items = root.findall("./channel/item")
    assert items
    enclosure = items[0].find("enclosure")
    assert enclosure is not None
    assert str(episode.id) in enclosure.attrib["url"]
    assert "token=feed_token_123456" in enclosure.attrib["url"]
    guid = items[0].find("guid")
    assert guid is not None
    assert guid.attrib.get("isPermaLink") == "false"


def test_feed_includes_ready_one_off_episode(client, tmp_path):
    digest_id, article_ids = _create_digest_with_articles(article_count=1)
    settings = get_settings()
    podcasts_dir = Path(settings.output_dir) / "podcasts"
    podcasts_dir.mkdir(parents=True, exist_ok=True)
    audio_path = podcasts_dir / f"one-off-{uuid4()}.mp3"
    audio_path.write_bytes(b"one-off-audio")
    with Session(engine) as session:
        prefs = podcast_service.get_or_create_preferences(session, user_id=None)
        prefs.podcast_feed_enabled = True
        prefs.podcast_feed_token = "feed_token_one_off_ready"
        user_id = prefs.user_id
        session.add(prefs)
        session.commit()

    episode = _create_episode(
        digest_id=digest_id,
        article_ids=article_ids,
        status="ready",
        audio_path=audio_path,
        trigger="one_off",
        user_id=user_id,
    )

    feed = client.get("/api/podcast/feed.xml?token=feed_token_one_off_ready")
    assert feed.status_code == 200
    root = ET.fromstring(feed.content)
    enclosure_urls = [
        enclosure.attrib["url"]
        for enclosure in root.findall("./channel/item/enclosure")
    ]
    assert any(str(episode.id) in url for url in enclosure_urls)


def test_feed_token_is_scoped_to_token_owner(client):
    digest_id, article_ids = _create_digest_with_articles(article_count=1)
    settings = get_settings()
    podcasts_dir = Path(settings.output_dir) / "podcasts"
    podcasts_dir.mkdir(parents=True, exist_ok=True)
    audio_a = podcasts_dir / f"episode-{uuid4()}.mp3"
    audio_b = podcasts_dir / f"episode-{uuid4()}.mp3"
    audio_a.write_bytes(b"user-a-audio")
    audio_b.write_bytes(b"user-b-audio")

    with Session(engine) as session:
        user_a = User(
            username=f"pod-a-{uuid4().hex[:8]}",
            password_hash="test-password-hash",
        )
        user_b = User(
            username=f"pod-b-{uuid4().hex[:8]}",
            password_hash="test-password-hash",
        )
        session.add(user_a)
        session.add(user_b)
        session.commit()
        session.refresh(user_a)
        session.refresh(user_b)
        user_a_id = user_a.id
        user_b_id = user_b.id

        session.add(
            PodcastPreferences(
                user_id=user_a_id,
                podcast_feed_enabled=True,
                podcast_feed_token="feed_token_user_a_scope",
            )
        )
        session.add(
            PodcastPreferences(
                user_id=user_b_id,
                podcast_feed_enabled=True,
                podcast_feed_token="feed_token_user_b_scope",
            )
        )
        session.commit()

    episode_a = _create_episode(
        digest_id=digest_id,
        article_ids=article_ids,
        status="ready",
        audio_path=audio_a,
        user_id=user_a_id,
    )
    episode_b = _create_episode(
        digest_id=digest_id,
        article_ids=article_ids,
        status="ready",
        audio_path=audio_b,
        user_id=user_b_id,
    )

    feed = client.get("/api/podcast/feed.xml?token=feed_token_user_b_scope")
    assert feed.status_code == 200
    root = ET.fromstring(feed.content)
    enclosures = root.findall("./channel/item/enclosure")
    enclosure_urls = [item.attrib["url"] for item in enclosures]
    assert any(str(episode_b.id) in url for url in enclosure_urls)
    assert all(str(episode_a.id) not in url for url in enclosure_urls)

    cross_download = client.get(
        f"/api/podcast/episodes/{episode_a.id}/download?token=feed_token_user_b_scope"
    )
    assert cross_download.status_code == 404

    cross_stream = client.get(
        f"/api/podcast/episodes/{episode_a.id}/stream?token=feed_token_user_b_scope"
    )
    assert cross_stream.status_code == 404

    own_download = client.get(
        f"/api/podcast/episodes/{episode_b.id}/download?token=feed_token_user_b_scope"
    )
    assert own_download.status_code == 200
    assert own_download.content == b"user-b-audio"


def test_feed_info_uses_authenticated_token_owner(client):
    user_a_id, _headers_a = _create_auth_headers_for_user("feed_info_owner_a")
    user_b_id, headers_b = _create_auth_headers_for_user("feed_info_owner_b")

    with Session(engine) as session:
        session.add(
            PodcastPreferences(
                user_id=user_a_id,
                podcast_feed_enabled=True,
                podcast_feed_token="feed_token_info_user_a",
            )
        )
        session.commit()

    info = client.get("/api/podcast/feed/info", headers=headers_b)
    assert info.status_code == 200
    feed_url = info.json()["feed_url"]
    assert "feed_token_info_user_a" not in feed_url

    with Session(engine) as session:
        prefs_b = session.exec(
            select(PodcastPreferences).where(PodcastPreferences.user_id == user_b_id)
        ).one()

    assert prefs_b.podcast_feed_token
    assert prefs_b.podcast_feed_token in feed_url


def test_feed_info_does_not_claim_legacy_preferences(client):
    _owner_id, _owner_headers = _create_auth_headers_for_user("feed_info_legacy_owner")
    user_id, headers = _create_auth_headers_for_user("feed_info_legacy_secondary")

    with Session(engine) as session:
        legacy_prefs = PodcastPreferences(
            user_id=None,
            podcast_feed_enabled=True,
            podcast_feed_token="feed_token_legacy_unowned",
            openai_api_key="legacy-sensitive-key",
        )
        session.add(legacy_prefs)
        session.commit()
        legacy_prefs_id = legacy_prefs.id

    info = client.get("/api/podcast/feed/info", headers=headers)
    assert info.status_code == 200
    feed_url = info.json()["feed_url"]
    assert "feed_token_legacy_unowned" not in feed_url

    with Session(engine) as session:
        legacy_prefs = session.get(PodcastPreferences, legacy_prefs_id)
        singleton_owner = session.exec(
            select(User).order_by(User.created_at.asc())
        ).first()
        prefs = session.exec(
            select(PodcastPreferences).where(PodcastPreferences.user_id == user_id)
        ).one()

    assert legacy_prefs is not None
    assert singleton_owner is not None
    assert legacy_prefs.user_id == singleton_owner.id
    assert legacy_prefs.user_id != user_id
    assert legacy_prefs.openai_api_key == "legacy-sensitive-key"
    assert prefs.podcast_feed_token
    assert prefs.podcast_feed_token in feed_url


def test_legacy_feed_migration_preserves_existing_episodes(client, auth_headers):
    with Session(engine) as session:
        owner = session.exec(select(User).order_by(User.created_at.asc())).first()
        assert owner is not None
        owner_id = owner.id

    digest_id, article_ids = _create_digest_with_articles(article_count=1)
    settings = get_settings()
    podcasts_dir = Path(settings.output_dir) / "podcasts"
    podcasts_dir.mkdir(parents=True, exist_ok=True)
    audio_path = podcasts_dir / f"legacy-{uuid4()}.mp3"
    audio_path.write_bytes(b"legacy-audio")

    with Session(engine) as session:
        session.add(
            PodcastPreferences(
                user_id=None,
                podcast_feed_enabled=True,
                podcast_feed_token="feed_token_legacy_history",
            )
        )
        session.commit()

    episode = _create_episode(
        digest_id=digest_id,
        article_ids=article_ids,
        status="ready",
        audio_path=audio_path,
        user_id=None,
    )

    prefs = client.get("/api/podcast/preferences", headers=auth_headers)
    assert prefs.status_code == 200

    feed = client.get("/api/podcast/feed.xml?token=feed_token_legacy_history")
    assert feed.status_code == 200
    root = ET.fromstring(feed.content)
    enclosure_urls = [
        enclosure.attrib["url"]
        for enclosure in root.findall("./channel/item/enclosure")
    ]
    assert any(str(episode.id) in url for url in enclosure_urls)

    with Session(engine) as session:
        migrated_episode = session.get(PodcastEpisode, episode.id)

    assert migrated_episode is not None
    assert migrated_episode.user_id == owner_id


def test_stream_and_download_reject_paths_outside_podcast_output_dir(client, tmp_path):
    digest_id, article_ids = _create_digest_with_articles(article_count=1)
    outside_audio = tmp_path / "outside.mp3"
    outside_audio.write_bytes(b"outside-audio")

    with Session(engine) as session:
        prefs = podcast_service.get_or_create_preferences(session, user_id=None)
        prefs.podcast_feed_enabled = True
        prefs.podcast_feed_token = "feed_token_path_guard"
        user_id = prefs.user_id
        session.add(prefs)
        session.commit()

    episode = _create_episode(
        digest_id=digest_id,
        article_ids=article_ids,
        status="ready",
        audio_path=outside_audio,
        user_id=user_id,
    )

    stream = client.get(
        f"/api/podcast/episodes/{episode.id}/stream?token=feed_token_path_guard",
    )
    assert stream.status_code == 403

    download = client.get(
        f"/api/podcast/episodes/{episode.id}/download?token=feed_token_path_guard",
    )
    assert download.status_code == 403


def test_feed_artwork_rejects_paths_outside_podcast_artwork_dir(client):
    outside_artwork = Path("/tmp/ghostwriter_outside_artwork.jpg")
    outside_artwork.write_bytes(b"not-an-image-but-path-guard-test")
    try:
        with Session(engine) as session:
            prefs = podcast_service.get_or_create_preferences(session, user_id=None)
            prefs.podcast_feed_enabled = True
            prefs.podcast_feed_token = "feed_token_bad_artwork_path"
            prefs.podcast_feed_artwork_path = str(outside_artwork)
            session.add(prefs)
            session.commit()

        artwork = client.get(
            "/api/podcast/feed/artwork?token=feed_token_bad_artwork_path"
        )
        assert artwork.status_code == 403
    finally:
        outside_artwork.unlink(missing_ok=True)


def test_feed_uses_configured_public_base_url(client):
    user_id, headers = _create_auth_headers_for_user("feed_public_base")
    digest_id, article_ids = _create_digest_with_articles(article_count=1)
    _create_episode(
        digest_id=digest_id,
        article_ids=article_ids,
        status="ready",
        user_id=user_id,
    )

    with Session(engine) as session:
        prefs = podcast_service.get_or_create_preferences(session, user_id=user_id)
        prefs.podcast_feed_enabled = True
        prefs.podcast_feed_token = "feed_token_public_url"
        prefs.podcast_feed_base_url = "https://podcasts.example.com"
        session.add(prefs)
        session.commit()

    feed = client.get("/api/podcast/feed.xml?token=feed_token_public_url")
    assert feed.status_code == 200
    root = ET.fromstring(feed.content)
    assert root.findtext("./channel/link") == "https://podcasts.example.com"
    enclosure = root.find("./channel/item/enclosure")
    assert enclosure is not None
    assert enclosure.attrib["url"].startswith("https://podcasts.example.com/")

    info = client.get("/api/podcast/feed/info", headers=headers)
    assert info.status_code == 200
    assert info.json()["feed_url"].startswith(
        "https://podcasts.example.com/api/podcast/feed.xml?token="
    )


def test_feed_artwork_upload_and_serve(client):
    user_id, headers = _create_auth_headers_for_user("artwork_upload")
    image = Image.new("RGB", (1500, 1500), color=(10, 20, 30))
    buffer = BytesIO()
    image.save(buffer, format="JPEG")
    buffer.seek(0)

    upload = client.post(
        "/api/podcast/feed/artwork",
        files={"file": ("artwork.jpg", buffer.getvalue(), "image/jpeg")},
        headers=headers,
    )
    assert upload.status_code == 200
    upload_payload = upload.json()
    assert upload_payload["status"] == "uploaded"
    assert upload_payload["width"] == 1500
    assert upload_payload["height"] == 1500

    with Session(engine) as session:
        prefs = podcast_service.get_or_create_preferences(session, user_id=user_id)
        prefs.podcast_feed_enabled = True
        prefs.updated_at = datetime.utcnow()
        token = prefs.podcast_feed_token
        session.add(prefs)
        session.commit()

    artwork = client.get(f"/api/podcast/feed/artwork?token={token}")
    assert artwork.status_code == 200
    assert artwork.headers["content-type"].startswith("image/")

    info = client.get("/api/podcast/feed/info", headers=headers)
    assert info.status_code == 200
    info_payload = info.json()
    assert "feed.xml?token=" in info_payload["feed_url"]


def test_feed_artwork_upload_authenticates_before_validation(client):
    _create_auth_headers_for_user("artwork_auth_guard")

    upload = client.post(
        "/api/podcast/feed/artwork",
        files={"file": ("not-image.txt", b"not image", "text/plain")},
    )
    assert upload.status_code == 401


def test_feed_artwork_upload_is_scoped_to_token_owner(client, tmp_path):
    owner_id, _owner_headers = _create_auth_headers_for_user("artwork_owner")
    user_id, headers = _create_auth_headers_for_user("artwork_secondary")
    owner_artwork = tmp_path / "owner.jpg"
    owner_artwork.write_bytes(b"owner-artwork")

    with Session(engine) as session:
        owner_prefs = podcast_service.get_or_create_preferences(
            session,
            user_id=owner_id,
        )
        owner_prefs.podcast_feed_enabled = True
        owner_prefs.podcast_feed_token = "feed_token_artwork_owner"
        owner_prefs.podcast_feed_artwork_path = str(owner_artwork)
        session.add(owner_prefs)
        session.commit()

    image = Image.new("RGB", (1500, 1500), color=(30, 20, 10))
    buffer = BytesIO()
    image.save(buffer, format="JPEG")

    upload = client.post(
        "/api/podcast/feed/artwork",
        files={"file": ("secondary.jpg", buffer.getvalue(), "image/jpeg")},
        headers=headers,
    )
    assert upload.status_code == 200

    with Session(engine) as session:
        owner_prefs = session.exec(
            select(PodcastPreferences).where(PodcastPreferences.user_id == owner_id)
        ).first()
        prefs = session.exec(
            select(PodcastPreferences).where(PodcastPreferences.user_id == user_id)
        ).one()

    assert owner_prefs is not None
    assert owner_prefs.podcast_feed_artwork_path == str(owner_artwork)
    assert prefs.podcast_feed_artwork_path
    assert prefs.podcast_feed_artwork_path != str(owner_artwork)


def test_scheduled_podcast_generation(monkeypatch):
    monkeypatch.setattr(
        podcast_service, "_schedule_episode_task", lambda _episode_id: None
    )
    digest_id, _ = _create_digest_with_articles(article_count=2)

    with Session(engine) as session:
        prefs = podcast_service.get_or_create_preferences(session, user_id=None)
        prefs.enabled = True
        prefs.schedule = "daily"
        prefs.schedule_time = "00:00"
        prefs.updated_at = datetime.utcnow()
        session.add(prefs)
        session.commit()

    episode_id = podcast_service.generate_scheduled_episode()
    assert episode_id is not None

    with Session(engine) as session:
        episode = session.get(PodcastEpisode, UUID(str(episode_id)))
        assert episode is not None
        assert str(digest_id) in episode.digest_ids
        assert episode.trigger == "scheduled"
        assert episode.status == "pending"


def test_scheduled_podcast_generation_excludes_one_off_digests(client, monkeypatch):
    monkeypatch.setattr(
        podcast_service, "_schedule_episode_task", lambda _episode_id: None
    )
    one_off_digest_id, _ = _create_digest_with_articles(
        article_count=2,
        feed_url="synthetic://one-off",
        feed_title=ONE_OFF_SOURCE_LABEL,
    )
    normal_digest_id, _ = _create_digest_with_articles(article_count=2)

    with Session(engine) as session:
        existing_scheduled = session.exec(
            select(PodcastEpisode).where(PodcastEpisode.trigger == "scheduled")
        ).all()
        for episode in existing_scheduled:
            session.delete(episode)
        prefs = podcast_service.get_or_create_preferences(session, user_id=None)
        prefs.enabled = True
        prefs.schedule = "daily"
        prefs.schedule_time = "00:00"
        prefs.updated_at = datetime.utcnow()
        session.add(prefs)
        session.commit()

    episode_id = podcast_service.generate_scheduled_episode()
    assert episode_id is not None

    with Session(engine) as session:
        episode = session.get(PodcastEpisode, UUID(str(episode_id)))
        assert episode is not None
        assert str(normal_digest_id) in episode.digest_ids
        assert str(one_off_digest_id) not in episode.digest_ids


def test_elevenlabs_tts_normalization_for_spoken_delivery():
    normalized = podcast_service._normalize_tts_segment_text(
        "Dr. Lee said revenue hit $42.50 at 14:30 on 2026-02-20 via https://example.com/path",
        provider="elevenlabs",
        elevenlabs_model_id="eleven_v3",
    )
    assert "Doctor Lee" in normalized
    assert "42 dollars and 50 cents" in normalized
    assert "2:30 PM" in normalized
    assert "February 20, 2026" in normalized
    assert "example dot com" in normalized


def test_eleven_v3_prompt_guidance_includes_sparse_audio_tag_rules():
    guidance = podcast_service._tts_script_delivery_guidance(
        provider="elevenlabs",
        elevenlabs_model_id="eleven_v3",
    )
    system_prompt = podcast_service._script_system_prompt_for_tts(
        provider="elevenlabs",
        elevenlabs_model_id="eleven_v3",
    )
    assert "audio/emotion tags" in guidance
    assert "one tag every 4-8 lines" in guidance
    assert "Do not overuse tags" in guidance
    assert "Keep tags sparse and intentional" in system_prompt


def test_article_scoring_prefers_podcast_worthy_source_material():
    flat = _podcast_test_article(
        title="Company posts routine update",
        content="The company posted a routine update with minor changes.",
        word_count=45,
    )
    rich = _podcast_test_article(
        title="New AI rollout: why customers are pushing back",
        content=(
            "The company announced a new AI rollout in 2026, but customers and critics "
            "raised concerns because the change could affect billing, privacy, and support. "
            "Revenue was $42.5 million last quarter, a 17% increase, while support tickets "
            "rose 31%. Analysts said the tradeoff is speed versus trust, and the result "
            "might shape how similar products launch later this year. "
        )
        * 10,
        word_count=850,
    )
    filtered = _test_podcast_preferences(filter_keywords=["privacy"])
    prefs = _test_podcast_preferences()

    flat_score = podcast_service.score_article(
        article=flat,
        prefs=prefs,
        feedback_profile={},
    )
    rich_score = podcast_service.score_article(
        article=rich,
        prefs=prefs,
        feedback_profile={},
    )
    filtered_score = podcast_service.score_article(
        article=rich,
        prefs=filtered,
        feedback_profile={},
    )

    assert rich_score > flat_score * 3
    assert filtered_score == 0


def test_balanced_article_selection_keeps_one_source_from_dominating():
    dominant = [
        _podcast_test_article(
            title=f"Dominant story {index}",
            content="New data shows a concrete 25% change and explains why it matters. " * 20,
            feed_title="Dominant",
            sort_order=index,
        )
        for index in range(5)
    ]
    alternatives = [
        _podcast_test_article(
            title="Different source one",
            content="A surprising result creates debate because it could affect readers. " * 20,
            feed_title="Alternative One",
            sort_order=10,
        ),
        _podcast_test_article(
            title="Different source two",
            content="A first-time launch reveals a concrete tradeoff with 14 teams involved. " * 20,
            feed_title="Alternative Two",
            sort_order=11,
        ),
    ]
    scored = [
        (10.0 - index, index, article)
        for index, article in enumerate([*dominant, *alternatives])
    ]

    selected = podcast_service._select_balanced_articles(scored, target_count=4)
    selected_sources = [article.feed_title for article in selected]

    assert selected_sources.count("Dominant") == 2
    assert "Alternative One" in selected_sources
    assert "Alternative Two" in selected_sources


def test_one_off_article_selection_preserves_submitted_order():
    digest_id = uuid4()
    feed_id = uuid4()
    articles = [
        DigestArticle(
            digest_id=digest_id,
            feed_id=feed_id,
            title=f"Submitted source {index}",
            url=f"one-off://source/{index}",
            mode="raw",
            word_count=8,
            ai_failed=False,
            processing_ms=0,
            content=f"Short but intentional submitted source {index}.",
            feed_title=ONE_OFF_SOURCE_LABEL,
            sort_order=index,
            content_type="article",
        )
        for index in range(3)
    ]
    with Session(engine) as session:
        feed = Feed(
            id=feed_id,
            url=f"synthetic://one-off-selection-{uuid4()}",
            title=ONE_OFF_SOURCE_LABEL,
            is_active=False,
            mode="raw",
            max_articles=0,
        )
        digest = Digest(
            id=digest_id,
            filename=f"one-off-selection-{uuid4()}.epub",
            period="manual",
            status="completed",
            stage="completed",
            article_count=len(articles),
        )
        session.add(feed)
        session.add(digest)
        for article in articles:
            session.add(article)
        session.commit()

        selected = podcast_service.select_articles_for_episode(
            session,
            digest_ids=[digest_id],
            prefs=_test_podcast_preferences(filter_keywords=["intentional"]),
            user_id=None,
            trigger="one_off",
        )

    assert [article.title for article in selected] == [
        "Submitted source 0",
        "Submitted source 1",
        "Submitted source 2",
    ]


def test_brief_parser_and_renderer_preserve_richer_podcast_context():
    raw = """
    {
      "briefs": [
        {
          "index": 1,
          "title": "AI rollout",
          "summary": "A company launched a new AI feature.",
          "key_points": ["Launch starts in June", "Customers can opt out"],
          "explainers": ["Opt-out means users keep the old workflow"],
          "why_it_matters": "It changes how customers interact with support.",
          "tension": "The company wants speed while customers want control.",
          "specific_details": ["31% more support tickets", "$42.5 million in revenue"],
          "listener_angle": "Listeners may see this in tools they use daily.",
          "follow_up_question": "Does faster automation justify less control?",
          "banter_hook": "Everyone loves an opt-out hidden three menus deep."
        }
      ]
    }
    """

    briefs = podcast_service._parse_chunk_briefs_json(raw)
    block = podcast_service._render_briefs_block(briefs)

    assert briefs[0]["specific_details"] == [
        "31% more support tickets",
        "$42.5 million in revenue",
    ]
    assert "Why it matters: It changes how customers interact with support." in block
    assert "Tension: The company wants speed while customers want control." in block
    assert "Follow-up question: Does faster automation justify less control?" in block


def test_queue_episode_generation_finds_existing_episode(monkeypatch):
    monkeypatch.setattr(
        podcast_service, "_schedule_episode_task", lambda _episode_id: None
    )
    digest_id, article_ids = _create_digest_with_articles(article_count=1)

    # Pre-create an episode for this digest
    existing = _create_episode(
        digest_id=digest_id, article_ids=article_ids, status="ready"
    )

    with Session(engine) as session:
        # Should find and return the existing episode instead of creating a new one
        episode = podcast_service.queue_episode_generation(session, digest_id=digest_id)

    assert episode.id == existing.id
    assert str(digest_id) in episode.digest_ids


def test_schedule_episode_task_uses_main_loop_when_called_without_running_loop(
    monkeypatch,
):
    scheduled: dict[str, object] = {}

    class _ClosedLoop:
        def is_closed(self) -> bool:
            return False

    def _fake_run_coroutine_threadsafe(coro, loop):
        scheduled["loop"] = loop
        scheduled["coroutine"] = coro

        class _Future:
            def add_done_callback(self, fn):
                scheduled["done_callback"] = fn

        return _Future()

    monkeypatch.setattr(
        "app.services.podcast_service.asyncio.get_running_loop",
        lambda: (_ for _ in ()).throw(RuntimeError("no running loop")),
    )
    monkeypatch.setattr(
        "app.services.podcast_service.asyncio.run_coroutine_threadsafe",
        _fake_run_coroutine_threadsafe,
    )

    podcast_service.set_event_loop(_ClosedLoop())
    podcast_service._schedule_episode_task(uuid4())

    assert "coroutine" in scheduled
    assert "loop" in scheduled


@pytest.mark.asyncio
async def test_elevenlabs_synthesis_includes_context_and_normalization_mode(
    monkeypatch,
):
    captured: dict[str, object] = {}

    class _Response:
        status_code = 200
        content = b"audio-bytes"
        text = ""

    class _Client:
        def __init__(self, *args, **kwargs):
            captured["timeout"] = kwargs.get("timeout")

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, endpoint, *, params=None, json=None, headers=None):
            captured["endpoint"] = endpoint
            captured["params"] = params
            captured["json"] = json
            captured["headers"] = headers
            return _Response()

    monkeypatch.setattr("app.services.podcast_service.httpx.AsyncClient", _Client)

    prefs = _test_podcast_preferences(
        tts_provider="elevenlabs",
        elevenlabs_model_id="eleven_v3",
        elevenlabs_api_key="xi-test-key",
        host_a_voice="voice_a",
        host_b_voice="voice_b",
    )

    result = await podcast_service._synthesize_segment_elevenlabs(
        text="Current line",
        voice="voice_a",
        prefs=prefs,
        previous_text="Previous context line",
        next_text="Next context line",
    )

    assert result == b"audio-bytes"
    payload = captured["json"]
    assert isinstance(payload, dict)
    assert payload["apply_text_normalization"] == "on"
    assert "previous_text" not in payload
    assert "next_text" not in payload


@pytest.mark.asyncio
async def test_elevenlabs_non_v3_synthesis_includes_context(monkeypatch):
    captured: dict[str, object] = {}

    class _Response:
        status_code = 200
        content = b"audio-bytes"
        text = ""

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, endpoint, *, params=None, json=None, headers=None):
            captured["json"] = json
            return _Response()

    monkeypatch.setattr("app.services.podcast_service.httpx.AsyncClient", _Client)

    prefs = _test_podcast_preferences(
        tts_provider="elevenlabs",
        elevenlabs_model_id="eleven_turbo_v2_5",
        elevenlabs_api_key="xi-test-key",
        host_a_voice="voice_a",
        host_b_voice="voice_b",
    )

    await podcast_service._synthesize_segment_elevenlabs(
        text="Current line",
        voice="voice_a",
        prefs=prefs,
        previous_text="Previous context line",
        next_text="Next context line",
    )

    payload = captured["json"]
    assert isinstance(payload, dict)
    assert payload["apply_text_normalization"] == "auto"
    assert payload["previous_text"] == "Previous context line"
    assert payload["next_text"] == "Next context line"


# ======================== Podcast Schedules CRUD ========================


def test_podcast_schedules_crud(client, auth_headers):
    """Full lifecycle: create, list, get, update, delete a podcast schedule."""
    # List: initially empty
    list_resp = client.get("/api/podcast/schedules", headers=auth_headers)
    assert list_resp.status_code == 200
    assert list_resp.json() == []

    # Create
    create_resp = client.post(
        "/api/podcast/schedules",
        json={
            "name": "Morning Tech",
            "days": ["monday", "wednesday", "friday"],
            "time": "07:30",
        },
        headers=auth_headers,
    )
    assert create_resp.status_code == 201
    created = create_resp.json()
    assert created["name"] == "Morning Tech"
    assert set(created["days"]) == {"monday", "wednesday", "friday"}
    assert created["time"] == "07:30"
    assert created["enabled"] is True
    schedule_id = created["id"]

    # Get
    get_resp = client.get(f"/api/podcast/schedules/{schedule_id}", headers=auth_headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == "Morning Tech"

    # List: now has one
    list_resp = client.get("/api/podcast/schedules", headers=auth_headers)
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    # Update
    update_resp = client.put(
        f"/api/podcast/schedules/{schedule_id}",
        json={
            "name": "Morning Briefing",
            "days": ["monday", "tuesday"],
            "time": "08:00",
        },
        headers=auth_headers,
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()
    assert updated["name"] == "Morning Briefing"
    assert set(updated["days"]) == {"monday", "tuesday"}
    assert updated["time"] == "08:00"

    # Delete
    delete_resp = client.delete(
        f"/api/podcast/schedules/{schedule_id}", headers=auth_headers
    )
    assert delete_resp.status_code == 204

    # Verify deleted
    get_resp = client.get(f"/api/podcast/schedules/{schedule_id}", headers=auth_headers)
    assert get_resp.status_code == 404


def test_podcast_schedule_validation(client, auth_headers):
    """Validate schedule creation constraints."""
    # No days
    resp = client.post(
        "/api/podcast/schedules",
        json={"name": "Bad", "days": [], "time": "08:00"},
        headers=auth_headers,
    )
    assert resp.status_code == 400

    # Invalid time format
    resp = client.post(
        "/api/podcast/schedules",
        json={"name": "Bad", "days": ["monday"], "time": "99:99"},
        headers=auth_headers,
    )
    assert resp.status_code == 400


def test_podcast_schedule_toggle_enabled(client, auth_headers):
    """Toggle a schedule's enabled state."""
    create = client.post(
        "/api/podcast/schedules",
        json={"name": "Toggle Test", "days": ["saturday"], "time": "10:00"},
        headers=auth_headers,
    )
    schedule_id = create.json()["id"]

    # Disable
    resp = client.put(
        f"/api/podcast/schedules/{schedule_id}",
        json={"enabled": False},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False

    # Re-enable
    resp = client.put(
        f"/api/podcast/schedules/{schedule_id}",
        json={"enabled": True},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["enabled"] is True


def test_podcast_schedule_trigger(client, monkeypatch, auth_headers):
    """Trigger podcast generation for a specific schedule."""
    monkeypatch.setattr(
        podcast_service, "_schedule_episode_task", lambda _episode_id: None
    )
    digest_id, _ = _create_digest_with_articles(article_count=2)

    create = client.post(
        "/api/podcast/schedules",
        json={"name": "Trigger Test", "days": ["monday"], "time": "09:00"},
        headers=auth_headers,
    )
    schedule_id = create.json()["id"]

    trigger = client.post(
        f"/api/podcast/schedules/{schedule_id}/trigger",
        headers=auth_headers,
    )
    assert trigger.status_code == 200
    payload = trigger.json()
    assert payload["status"] == "pending"
    assert str(digest_id) in payload["digest_ids"]

    # Verify schedule tracking was updated
    with Session(engine) as session:
        sched = session.get(PodcastSchedule, UUID(schedule_id))
        assert sched is not None
        assert sched.last_run_at is not None
        assert sched.last_episode_id is not None


def test_generate_episode_for_schedule_only_includes_new_digests(monkeypatch):
    """Verify that only digests created after last_run_at are included."""
    from datetime import timedelta

    monkeypatch.setattr(
        podcast_service, "_schedule_episode_task", lambda _episode_id: None
    )

    # Create an older digest
    old_time = datetime.utcnow() - timedelta(hours=2)
    _create_digest_with_articles(article_count=1, completed_at=old_time)

    # Create a schedule with last_run_at after the old digest
    last_run = datetime.utcnow()
    with Session(engine) as session:
        sched = PodcastSchedule(
            name="Filter Test",
            days=["monday"],
            time="08:00",
            enabled=True,
            last_run_at=last_run,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        session.add(sched)
        session.commit()
        session.refresh(sched)
        schedule_id = sched.id

    # No new digests since last_run_at -> should return None
    result = podcast_service.generate_episode_for_schedule(schedule_id)
    assert result is None

    # Create a new digest after last_run_at
    new_digest_id, _ = _create_digest_with_articles(
        article_count=2,
        completed_at=last_run + timedelta(seconds=1),
    )

    # Now it should find the new digest and generate
    result = podcast_service.generate_episode_for_schedule(schedule_id)
    assert result is not None

    with Session(engine) as session:
        episode = session.get(PodcastEpisode, result)
        assert episode is not None
        assert str(new_digest_id) in episode.digest_ids


def test_generate_episode_for_schedule_excludes_one_off_digests(client, monkeypatch):
    """Verify that manual schedule triggers ignore one-off source digests."""
    from datetime import timedelta

    monkeypatch.setattr(
        podcast_service, "_schedule_episode_task", lambda _episode_id: None
    )

    last_run = datetime.utcnow() + timedelta(days=1)
    with Session(engine) as session:
        sched = PodcastSchedule(
            name="One-off Filter Test",
            days=["monday"],
            time="08:00",
            enabled=True,
            last_run_at=last_run,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        session.add(sched)
        session.commit()
        session.refresh(sched)
        schedule_id = sched.id

    _create_digest_with_articles(
        article_count=2,
        completed_at=last_run + timedelta(seconds=1),
        feed_url="synthetic://one-off",
        feed_title=ONE_OFF_SOURCE_LABEL,
    )

    result = podcast_service.generate_episode_for_schedule(schedule_id)
    assert result is None
