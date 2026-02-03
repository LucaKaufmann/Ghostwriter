from datetime import datetime, timedelta

from sqlmodel import Session

from app.models.digest import Digest, DigestArticle
from app.models.feed import Feed
from app.models.schedule import Schedule


def _create_schedule_rows(session: Session) -> None:
    periods = ["morning", "noon", "evening"]
    for idx, period in enumerate(periods):
        session.add(
            Schedule(
                period=period,
                hour=7 + idx,
                minute=0,
                enabled=True,
                timezone="UTC",
            )
        )
    session.commit()


def test_combined_sync_excludes_known_digest_ids(client):
    from app.core.database import engine

    with Session(engine) as session:
        feed = Feed(url="https://example.com/feed.xml", title="Feed", is_active=True)
        session.add(feed)

        digest1 = Digest(
            filename="2025-01-01_morning.epub",
            period="morning",
            status="completed",
            stage="completed",
            article_count=1,
            created_at=datetime.utcnow() - timedelta(days=2),
            completed_at=datetime.utcnow() - timedelta(days=2),
        )
        digest2 = Digest(
            filename="2025-01-02_morning.epub",
            period="morning",
            status="completed",
            stage="completed",
            article_count=1,
            created_at=datetime.utcnow() - timedelta(days=1),
            completed_at=datetime.utcnow() - timedelta(days=1),
        )
        session.add(digest1)
        session.add(digest2)
        session.commit()
        digest1_id = digest1.id
        digest2_id = digest2.id

        article1 = DigestArticle(
            digest_id=digest1_id,
            feed_id=feed.id,
            title="Article 1",
            url="https://example.com/a1",
            mode="raw",
            word_count=10,
            content="Content 1",
            feed_title="Feed",
            sort_order=0,
        )
        article2 = DigestArticle(
            digest_id=digest2_id,
            feed_id=feed.id,
            title="Article 2",
            url="https://example.com/a2",
            mode="raw",
            word_count=10,
            content="Content 2",
            feed_title="Feed",
            sort_order=0,
        )
        session.add(article1)
        session.add(article2)
        _create_schedule_rows(session)

    response = client.get(f"/api/sync?digest_ids={digest1_id}")
    assert response.status_code == 200

    payload = response.json()
    assert "config" in payload
    assert "feeds" in payload
    assert "digests" in payload
    assert "schedules" in payload

    digests = payload["digests"]["new_digests"]
    assert len(digests) == 1
    assert digests[0]["id"] == str(digest2_id)
    assert len(digests[0]["articles"]) == 1
    assert digests[0]["articles"][0]["title"] == "Article 2"
