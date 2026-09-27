"""End-to-end API journey with real DB, EPUB, PDF, audio file and private RSS."""

from __future__ import annotations

import asyncio
import sys
import time
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, create_engine, select

from app.core.auth import generate_api_token, get_token_prefix, hash_api_token
from app.core.config import get_settings
from app.core.database import engine as shared_engine
from app.main import app
from app.models.api_token import APIToken
from app.models.digest import Digest, DigestArticle
from app.models.podcast_episode import PodcastEpisode
from app.models.user import User
from app.services.podcast_service import podcast_service
from app.worker.cleanup import cleanup_old_digests
from tests.fixtures.journey_harness import ARTICLE_TEXT, ARTICLE_TITLE, install


def _terminal(client, url: str, headers: dict, terminal: set[str]) -> dict:
    deadline = time.monotonic() + 12
    for _ in range(60):
        response = client.get(url, headers=headers)
        assert response.status_code == 200, response.text
        data = response.json()
        status = data.get("status") or data.get("episode", {}).get("status")
        if status in terminal:
            return data
        assert time.monotonic() < deadline, data
        time.sleep(0.1)
    raise AssertionError("Generation exceeded 60 bounded polls")


@pytest.fixture
def journey_client(tmp_path, monkeypatch):
    """Use a separate database even when the entire backend suite runs together."""
    settings = get_settings()
    for field in ("data_dir", "output_dir", "logs_dir"):
        path = tmp_path / field
        path.mkdir()
        monkeypatch.setattr(settings, field, str(path))
    isolated_engine = create_engine(
        f"sqlite:///{tmp_path / 'journey.db'}",
        connect_args={"check_same_thread": False},
    )
    # Existing API and worker modules import engine by value. Redirect each
    # reference in this fixture only, then restore it through monkeypatch.
    for name, module in tuple(sys.modules.items()):
        if name.startswith("app.") and getattr(module, "engine", None) is shared_engine:
            monkeypatch.setattr(module, "engine", isolated_engine)
    monkeypatch.setattr(sys.modules["tests.fixtures.journey_harness"], "engine", isolated_engine)
    with TestClient(app) as client:
        yield client, isolated_engine
    isolated_engine.dispose()


def test_reading_listening_journey(journey_client, monkeypatch):
    client, engine = journey_client
    output = Path(get_settings().output_dir)
    calls = install(monkeypatch, output)

    registered = client.post(
        "/api/auth/register",
        json={"username": "journey", "password": "journey-password-123"},
    )
    assert registered.status_code == 200, registered.text
    token = registered.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    start = client.post("/api/digests/trigger", json={"period": "manual"}, headers=headers)
    assert start.status_code == 200, start.text
    digest_id = UUID(start.json()["id"])
    completed = _terminal(client, f"/api/digests/{digest_id}/status", headers, {"completed", "failed"})
    assert completed["status"] == "completed", completed
    with Session(engine) as session:
        digest = session.get(Digest, digest_id)
        articles = session.exec(select(DigestArticle).where(DigestArticle.digest_id == digest.id)).all()
        assert digest.article_count == 1 and len(articles) == 1
        assert ARTICLE_TEXT[:60] in articles[0].content
        filename = digest.filename
        article_id = articles[0].id

    reading = client.get(f"/api/digests/{digest_id}/articles", headers=headers)
    assert reading.status_code == 200
    assert reading.json()["articles"][0]["title"] == ARTICLE_TITLE
    assert ARTICLE_TEXT[:60] in reading.json()["articles"][0]["content_html"]
    epub = client.get(f"/api/digests/{digest_id}/download?format=epub", headers=headers)
    assert epub.status_code == 200
    with zipfile.ZipFile(BytesIO(epub.content)) as book:
        chapter_text = " ".join(
            book.read(name).decode("utf-8")
            for name in book.namelist() if name.endswith(".xhtml")
        )
    assert ARTICLE_TITLE in chapter_text and ARTICLE_TEXT[:60] in chapter_text
    pdf = client.get(f"/api/digests/{digest_id}/download?format=pdf", headers=headers)
    assert pdf.status_code == 200, pdf.text[:300]
    assert pdf.content.startswith(b"%PDF")
    assert b"%%EOF" in pdf.content[-64:]
    assert len(pdf.content) > 1000

    prefs = client.put(
        "/api/podcast/preferences",
        json={"podcast_feed_enabled": True}, headers=headers,
    )
    assert prefs.status_code == 200, prefs.text
    queued = client.post(f"/api/digests/{digest_id}/podcast", headers=headers)
    assert queued.status_code == 200, queued.text
    episode_id = UUID(queued.json()["episode_id"])
    failed = _terminal(client, f"/api/digests/{digest_id}/podcast", headers, {"failed", "ready"})
    assert failed["episode"]["status"] == "failed", failed
    assert "Synthetic provider interruption" in failed["episode"]["error_message"]
    retried = client.post(f"/api/podcast/episodes/{episode_id}/retry", headers=headers)
    assert retried.status_code == 200, retried.text
    ready = _terminal(client, f"/api/digests/{digest_id}/podcast", headers, {"ready", "failed"})
    assert ready["episode"]["status"] == "ready", ready
    assert calls["audio"] == 2
    with Session(engine) as session:
        episode = session.get(PodcastEpisode, episode_id)
        assert str(digest_id) in episode.digest_ids
        assert str(article_id) in episode.article_ids
        assert Path(episode.audio_path).is_file()
        digest = session.get(Digest, digest_id)
        digest.created_at = datetime.utcnow() - timedelta(days=30)
        session.add(digest)
        session.commit()

    stream = client.get(f"/api/podcast/episodes/{episode_id}/stream")
    assert stream.status_code in {401, 403}
    assert client.get("/api/podcast/feed.xml?token=wrongtoken").status_code == 401
    feed_info = client.get("/api/podcast/feed/info", headers=headers)
    assert feed_info.status_code == 200
    private_url = feed_info.json()["feed_url"]
    private_feed = client.get(private_url)
    assert private_feed.status_code == 200
    assert ARTICLE_TITLE in private_feed.text
    assert ET.fromstring(private_feed.content).find("./channel/item/enclosure") is not None
    assert client.get(f"/api/podcast/episodes/{episode_id}/stream", headers=headers).status_code == 200
    with Session(engine) as session:
        outsider = User(username="journey-outsider", password_hash="unused", is_admin=False)
        session.add(outsider)
        session.flush()
        outsider_token = generate_api_token()
        session.add(APIToken(
            user_id=outsider.id,
            name="journey-outsider",
            token_hash=hash_api_token(outsider_token),
            token_prefix=get_token_prefix(outsider_token),
        ))
        outsider_prefs = podcast_service.get_or_create_preferences(session, user_id=outsider.id)
        outsider_prefs.podcast_feed_enabled = True
        session.add(outsider_prefs)
        outsider_feed_token = outsider_prefs.podcast_feed_token
        session.commit()
    outsider_headers = {"X-API-Key": outsider_token}
    assert client.get("/api/podcast/episodes", headers=outsider_headers).json() == []
    assert client.get(f"/api/podcast/episodes/{episode_id}", headers=outsider_headers).status_code == 404
    assert client.get(
        f"/api/podcast/episodes/{episode_id}/download?token={outsider_feed_token}"
    ).status_code == 404

    # A podcast still references the digest: both retention paths preserve it.
    assert client.delete(f"/api/digests/{filename}", headers=headers).status_code == 409
    assert asyncio.run(cleanup_old_digests()) == 0
    with Session(engine) as session:
        assert session.get(Digest, digest_id) is not None
        assert session.get(DigestArticle, article_id) is not None
