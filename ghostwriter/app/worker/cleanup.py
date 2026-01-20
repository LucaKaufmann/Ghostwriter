"""Cleanup tasks for old digests and seen articles."""

import logging
import os
from datetime import datetime, timedelta

from sqlmodel import Session, select

from app.core.config import get_settings
from app.core.database import engine
from app.models.digest import Digest
from app.models.seen_article import SeenArticle

logger = logging.getLogger(__name__)


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
