from datetime import datetime, timedelta
import importlib

import pytest
from sqlmodel import Session, select

from app.core.config import Settings
from app.models.digest import Digest
from app.models.feed import Feed
from app.models.seen_article import SeenArticle


@pytest.mark.asyncio
async def test_cleanup_old_digests_removes_files(client, tmp_path, monkeypatch):
    from app.core.database import engine
    import app.worker.cleanup as cleanup
    cleanup = importlib.reload(cleanup)
    cleanup_old_digests = cleanup.cleanup_old_digests

    settings = Settings(output_dir=str(tmp_path))
    old_date = datetime.utcnow() - timedelta(days=settings.digest_retention_days + 1)

    filename = "old_digest.epub"
    output_file = tmp_path / filename
    output_file.write_text("dummy")

    with Session(engine) as session:
        digest = Digest(
            filename=filename,
            period="morning",
            status="completed",
            stage="completed",
            article_count=0,
            created_at=old_date,
            completed_at=old_date,
        )
        session.add(digest)
        session.commit()

    monkeypatch.setattr("app.worker.cleanup.get_settings", lambda: settings)

    cleaned = await cleanup_old_digests()
    assert cleaned == 1
    assert not output_file.exists()

    with Session(engine) as session:
        remaining = session.exec(select(Digest)).all()
        assert remaining == []


@pytest.mark.asyncio
async def test_cleanup_seen_articles(client, monkeypatch):
    from app.core.database import engine
    import app.worker.cleanup as cleanup
    cleanup = importlib.reload(cleanup)
    cleanup_seen_articles = cleanup.cleanup_seen_articles

    settings = Settings()
    monkeypatch.setattr("app.worker.cleanup.get_settings", lambda: settings)

    with Session(engine) as session:
        feed = Feed(url="https://example.com/feed.xml", title="Feed")
        session.add(feed)
        session.commit()
        session.refresh(feed)

        old_seen = SeenArticle(
            feed_id=feed.id,
            guid="old",
            url="https://example.com/a1",
            title="Old",
            seen_at=datetime.utcnow() - timedelta(days=60),
        )
        session.add(old_seen)
        session.commit()

    cleaned = await cleanup_seen_articles()
    assert cleaned == 1

    with Session(engine) as session:
        remaining = session.exec(select(SeenArticle)).all()
        assert remaining == []


@pytest.mark.asyncio
async def test_cleanup_old_tombstones(client):
    from app.core.database import engine
    import app.worker.cleanup as cleanup
    cleanup = importlib.reload(cleanup)
    TOMBSTONE_RETENTION_DAYS = cleanup.TOMBSTONE_RETENTION_DAYS
    cleanup_old_tombstones = cleanup.cleanup_old_tombstones

    with Session(engine) as session:
        tombstone = Feed(
            url="https://example.com/tombstone.xml",
            title="Tombstone",
            is_active=False,
            deleted_at=datetime.utcnow() - timedelta(days=TOMBSTONE_RETENTION_DAYS + 1),
        )
        session.add(tombstone)
        session.commit()

    cleaned = await cleanup_old_tombstones()
    assert cleaned == 1
