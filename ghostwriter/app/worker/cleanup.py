"""Cleanup tasks for old digests, seen articles, tombstones, and inactivity checking."""

import logging
import os
from datetime import datetime, timedelta

from sqlmodel import Session, select

from app.core.config import get_settings
from app.core.database import engine
from app.core.logging import digest_logger
from app.models.digest import Digest
from app.models.feed import Feed
from app.models.podcast_episode import PodcastEpisode
from app.models.seen_article import SeenArticle

logger = logging.getLogger(__name__)

# Tombstones are kept for 30 days before hard deletion
TOMBSTONE_RETENTION_DAYS = 30


async def check_client_inactivity() -> bool:
    """
    Check for client inactivity and auto-disable schedules if needed.

    This should be called daily to check if the client has been
    inactive for too long (no heartbeats, downloads, or feed syncs).

    Returns:
        True if schedules were disabled due to inactivity.
    """
    from app.services import activity_tracker

    try:
        disabled = activity_tracker.check_inactivity()
        days_inactive = activity_tracker.get_days_since_activity()
        if disabled:
            logger.warning("Schedules auto-disabled due to client inactivity")
        digest_logger.client_inactivity_check(days_inactive, disabled)
        return disabled
    except Exception as e:
        logger.error(f"Error checking client inactivity: {e}")
        return False


async def cleanup_old_digests() -> int:
    """
    Delete old EPUB files and digest records.

    Returns:
        Number of digests cleaned up.
    """
    settings = get_settings()
    cutoff = datetime.utcnow() - timedelta(days=settings.digest_retention_days)
    cleaned = 0

    with Session(engine) as session:
        # Find old completed digests
        statement = select(Digest).where(
            Digest.status == "completed",
            Digest.created_at < cutoff,
        )

        for digest in session.exec(statement).all():
            # Delete EPUB file
            epub_path = os.path.join(settings.output_dir, digest.filename)
            if os.path.exists(epub_path):
                try:
                    os.remove(epub_path)
                    logger.info(f"Deleted EPUB: {epub_path}")
                except OSError as e:
                    logger.error(f"Failed to delete {epub_path}: {e}")

            # Delete digest record
            session.delete(digest)
            cleaned += 1

        session.commit()

    logger.info(f"Cleaned up {cleaned} old digests")
    return cleaned


async def cleanup_old_podcast_episodes() -> int:
    """
    Delete old podcast audio files and episode records.

    Uses the same retention window as digests.

    Returns:
        Number of episodes cleaned up.
    """
    settings = get_settings()
    cutoff = datetime.utcnow() - timedelta(days=settings.digest_retention_days)
    cleaned = 0

    with Session(engine) as session:
        statement = select(PodcastEpisode).where(PodcastEpisode.created_at < cutoff)
        for episode in session.exec(statement).all():
            if episode.audio_path and os.path.exists(episode.audio_path):
                try:
                    os.remove(episode.audio_path)
                    logger.info(f"Deleted podcast audio: {episode.audio_path}")
                except OSError as e:
                    logger.error(f"Failed to delete podcast audio {episode.audio_path}: {e}")
            session.delete(episode)
            cleaned += 1
        session.commit()

    if cleaned > 0:
        logger.info(f"Cleaned up {cleaned} old podcast episodes")
    return cleaned


async def cleanup_seen_articles() -> int:
    """
    Delete old seen article records.

    Returns:
        Number of records cleaned up.
    """
    settings = get_settings()
    cutoff = datetime.utcnow() - timedelta(days=settings.seen_article_retention_days)
    cleaned = 0

    with Session(engine) as session:
        statement = select(SeenArticle).where(SeenArticle.seen_at < cutoff)

        for article in session.exec(statement).all():
            session.delete(article)
            cleaned += 1

        session.commit()

    logger.info(f"Cleaned up {cleaned} old seen article records")
    return cleaned


async def cleanup_old_tombstones() -> int:
    """
    Hard delete feed tombstones older than TOMBSTONE_RETENTION_DAYS.

    Tombstones are kept for 30 days to allow clients to sync deletions.
    After that, they are permanently removed from the database.

    Returns:
        Number of tombstones cleaned up.
    """
    cutoff = datetime.utcnow() - timedelta(days=TOMBSTONE_RETENTION_DAYS)
    cleaned = 0

    with Session(engine) as session:
        statement = select(Feed).where(
            Feed.deleted_at != None,  # noqa: E711
            Feed.deleted_at < cutoff,
        )

        for feed in session.exec(statement).all():
            logger.info(f"Hard deleting tombstoned feed: {feed.url}")
            session.delete(feed)
            cleaned += 1

        session.commit()

    if cleaned > 0:
        logger.info(f"Cleaned up {cleaned} old feed tombstones")

    return cleaned
