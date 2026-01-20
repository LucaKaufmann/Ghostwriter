"""The Bindery Pipeline - Core digest generation logic."""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID

from sqlmodel import Session, select

from app.core.config import get_settings
from app.core.database import engine
from app.models.digest import Digest, DigestArticle
from app.models.feed import Feed
from app.models.seen_article import SeenArticle
from app.services.content_processor import ContentProcessor, ExtractedArticle
from app.services.epub_generator import EpubGenerator
from app.services.llm_service import LLMService

logger = logging.getLogger(__name__)


class BinderyPipeline:
    """
    The Bindery Pipeline orchestrates digest generation.

    Pipeline stages:
    1. Fetch - Pull RSS feeds
    2. Extract - Get article content via Trafilatura
    3. Enrich - AI summarization (if enabled)
    4. Compile - Generate EPUB
    """

    def __init__(self, digest_id: UUID) -> None:
        """
        Initialize the pipeline for a specific digest.

        Args:
            digest_id: The digest being processed.
        """
        self.digest_id = digest_id
        self.settings = get_settings()
        self.content_processor = ContentProcessor(self.settings)
        self.llm_service = LLMService(self.settings)
        self.epub_generator = EpubGenerator(self.settings)

    async def run(self) -> None:
        """Execute the full pipeline."""
        try:
            await self._update_stage("fetching")
            feeds = await self._get_active_feeds()

            if not feeds:
                logger.warning("No active feeds found")
                await self._complete(0)
                return

            await self._update_progress(total_feeds=len(feeds))

            # Stage 1: Fetch all feeds
            all_articles = []
            for feed in feeds:
                articles = await self._fetch_feed(feed)
                all_articles.extend(articles)

                await self._update_progress(feeds_fetched=self._get_feeds_fetched() + 1)

                # Delay between feeds
                await asyncio.sleep(self.settings.fetch_delay_ms / 1000)

            if not all_articles:
                logger.warning("No new articles found")
                await self._complete(0)
                return

            # Cap total articles
            all_articles = all_articles[: self.settings.max_articles_per_digest]
            await self._update_progress(total_articles=len(all_articles))

            # Stage 2 & 3: Extract and enrich
            await self._update_stage("extracting")
            extracted_articles = []

            for article_data in all_articles:
                feed, parsed_article = article_data
                start_time = time.time()

                content = await self.content_processor.extract_content(parsed_article.url)
                if not content:
                    logger.warning(f"Could not extract: {parsed_article.url}")
                    continue

                word_count = ContentProcessor.count_words(content)

                # Enrich with AI if enabled
                is_summary = False
                ai_failed = False

                if feed.mode == "summarize":
                    await self._update_stage("enriching")
                    content, ai_failed = await self.llm_service.summarize(content)
                    is_summary = not ai_failed
                    if is_summary:
                        word_count = ContentProcessor.count_words(content)

                processing_ms = int((time.time() - start_time) * 1000)

                extracted = ExtractedArticle(
                    guid=parsed_article.guid,
                    url=parsed_article.url,
                    title=parsed_article.title,
                    content=content,
                    author=parsed_article.author,
                    word_count=word_count,
                    is_summary=is_summary,
                    ai_failed=ai_failed,
                    processing_ms=processing_ms,
                )
                extracted_articles.append((feed, extracted))

                # Mark article as seen
                await self._mark_seen(feed.id, parsed_article)

                await self._update_progress(
                    articles_enriched=self._get_articles_enriched() + 1
                )

            if not extracted_articles:
                logger.warning("No articles extracted successfully")
                await self._complete(0)
                return

            # Stage 4: Compile EPUB
            await self._update_stage("compiling")

            # Get just the articles for EPUB generation
            articles_for_epub = [a for _, a in extracted_articles]

            with Session(engine) as session:
                digest = session.get(Digest, self.digest_id)
                period = digest.period if digest else "manual"

            epub_path = self.epub_generator.generate(
                articles_for_epub, period=period
            )

            # Save DigestArticle records
            await self._save_article_records(extracted_articles)

            await self._complete(len(extracted_articles), epub_path)

        except Exception as e:
            logger.exception(f"Pipeline failed: {e}")
            await self._fail(str(e))
            raise

    async def _get_active_feeds(self) -> list[Feed]:
        """Get all active feeds."""
        with Session(engine) as session:
            statement = select(Feed).where(Feed.is_active == True)
            return list(session.exec(statement).all())

    async def _fetch_feed(self, feed: Feed) -> list[tuple[Feed, any]]:
        """
        Fetch and filter articles from a feed.

        Args:
            feed: The feed to process.

        Returns:
            List of (feed, parsed_article) tuples.
        """
        parsed = await self.content_processor.parse_feed(feed.url)

        # Filter out already seen articles
        new_articles = []
        for article in parsed:
            if not await self._is_seen(feed.id, article.guid):
                new_articles.append((feed, article))

        logger.info(
            f"Feed {feed.title}: {len(parsed)} total, {len(new_articles)} new"
        )
        return new_articles

    async def _is_seen(self, feed_id: UUID, guid: str) -> bool:
        """Check if an article has been seen recently."""
        cutoff = datetime.utcnow() - timedelta(
            days=self.settings.seen_article_retention_days
        )

        with Session(engine) as session:
            statement = (
                select(SeenArticle)
                .where(SeenArticle.feed_id == feed_id)
                .where(SeenArticle.guid == guid)
                .where(SeenArticle.seen_at > cutoff)
            )
            return session.exec(statement).first() is not None

    async def _mark_seen(self, feed_id: UUID, article: any) -> None:
        """Mark an article as seen."""
        with Session(engine) as session:
            seen = SeenArticle(
                feed_id=feed_id,
                guid=article.guid,
                url=article.url,
                title=article.title,
            )
            session.add(seen)
            session.commit()

    async def _save_article_records(
        self, articles: list[tuple[Feed, ExtractedArticle]]
    ) -> None:
        """Save DigestArticle records for audit trail."""
        with Session(engine) as session:
            for feed, article in articles:
                record = DigestArticle(
                    digest_id=self.digest_id,
                    feed_id=feed.id,
                    title=article.title,
                    url=article.url,
                    mode="summarized" if article.is_summary else "raw",
                    word_count=article.word_count,
                    ai_failed=article.ai_failed,
                    processing_ms=article.processing_ms,
                )
                session.add(record)
            session.commit()

    async def _update_stage(self, stage: str) -> None:
        """Update the current pipeline stage."""
        with Session(engine) as session:
            digest = session.get(Digest, self.digest_id)
            if digest:
                digest.stage = stage
                digest.status = "processing"
                session.add(digest)
                session.commit()
        logger.info(f"Pipeline stage: {stage}")

    async def _update_progress(self, **kwargs) -> None:
        """Update progress counters."""
        with Session(engine) as session:
            digest = session.get(Digest, self.digest_id)
            if digest:
                for key, value in kwargs.items():
                    setattr(digest, key, value)
                session.add(digest)
                session.commit()

    def _get_feeds_fetched(self) -> int:
        """Get current feeds_fetched count."""
        with Session(engine) as session:
            digest = session.get(Digest, self.digest_id)
            return digest.feeds_fetched if digest else 0

    def _get_articles_enriched(self) -> int:
        """Get current articles_enriched count."""
        with Session(engine) as session:
            digest = session.get(Digest, self.digest_id)
            return digest.articles_enriched if digest else 0

    async def _complete(self, article_count: int, epub_path: str | None = None) -> None:
        """Mark digest as completed."""
        with Session(engine) as session:
            digest = session.get(Digest, self.digest_id)
            if digest:
                digest.status = "completed"
                digest.stage = "completed"
                digest.completed_at = datetime.utcnow()
                digest.article_count = article_count
                digest.locked_at = None
                digest.locked_by = None
                session.add(digest)
                session.commit()
        logger.info(f"Digest completed with {article_count} articles")

    async def _fail(self, error: str) -> None:
        """Mark digest as failed."""
        with Session(engine) as session:
            digest = session.get(Digest, self.digest_id)
            if digest:
                digest.status = "failed"
                digest.error_message = error[:500]  # Truncate
                digest.locked_at = None
                digest.locked_by = None
                session.add(digest)
                session.commit()
        logger.error(f"Digest failed: {error}")


async def generate_digest(
    period: Literal["morning", "noon", "evening", "manual"] = "manual",
) -> UUID | None:
    """
    Start a digest generation job.

    Args:
        period: The time period for the digest.

    Returns:
        The digest ID if started, None if a job is already running.
    """
    settings = get_settings()

    with Session(engine) as session:
        # Check for running jobs (with 30-minute stale lock timeout)
        stale_cutoff = datetime.utcnow() - timedelta(minutes=30)

        statement = select(Digest).where(
            Digest.status == "processing",
            Digest.locked_at > stale_cutoff,
        )
        running = session.exec(statement).first()

        if running:
            logger.warning(f"Job already running: {running.id}")
            return None

        # Release any stale locks
        stale_statement = select(Digest).where(
            Digest.status == "processing",
            Digest.locked_at <= stale_cutoff,
        )
        for stale in session.exec(stale_statement).all():
            stale.status = "failed"
            stale.error_message = "Stale lock released"
            stale.locked_at = None
            session.add(stale)

        # Create new digest
        now = datetime.utcnow()
        digest = Digest(
            filename=f"{now.strftime('%Y-%m-%d')}_{period}.epub",
            period=period,
            status="processing",
            stage="queued",
            locked_at=now,
            locked_by="ghostwriter",
        )
        session.add(digest)
        session.commit()
        session.refresh(digest)
        digest_id = digest.id

    # Run pipeline in background
    pipeline = BinderyPipeline(digest_id)
    asyncio.create_task(pipeline.run())

    logger.info(f"Started digest generation: {digest_id}")
    return digest_id
