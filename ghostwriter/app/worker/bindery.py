"""The Bindery Pipeline - Core digest generation logic."""

import asyncio
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID

from sqlmodel import Session, select

from app.core.config import get_settings
from app.core.database import engine
from app.core.logging import digest_logger
from app.models.digest import Digest, DigestArticle
from app.models.feed import Feed
from app.models.seen_article import SeenArticle
from app.services.content_processor import ContentProcessor, ExtractedArticle
from app.services.epub_generator import EpubGenerator
from app.services.llm_service import LLMService
from app.services.newsletter_service import NewsletterService
from app.services.wallabag_service import WallabagService

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
        self.start_time: float | None = None

    async def run(self) -> None:
        """Execute the full pipeline."""
        self.start_time = time.time()

        # Get digest info for logging
        with Session(engine) as session:
            digest = session.get(Digest, self.digest_id)
            period = digest.period if digest else "manual"

        try:
            await self._update_stage("fetching")
            feeds = await self._get_active_feeds()

            if not feeds:
                logger.warning("No active feeds found")
                digest_logger.pipeline_no_articles(str(self.digest_id), "No active feeds configured")
                await self._complete(0)
                return

            await self._update_progress(total_feeds=len(feeds))
            digest_logger.pipeline_stage(
                "fetching",
                str(self.digest_id),
                feeds_count=len(feeds),
            )

            # Stage 1: Fetch all feeds
            all_articles = []
            for feed in feeds:
                feed_start = time.time()
                digest_logger.feed_fetch_started(feed.title, feed.url)

                try:
                    articles, total_in_feed = await self._fetch_feed(feed)
                    all_articles.extend(articles)
                    fetch_time_ms = int((time.time() - feed_start) * 1000)

                    digest_logger.feed_fetch_completed(
                        feed.title,
                        total_articles=total_in_feed,
                        new_articles=len(articles),
                        fetch_time_ms=fetch_time_ms,
                    )
                except Exception as e:
                    digest_logger.feed_fetch_failed(feed.title, feed.url, str(e))

                await self._update_progress(feeds_fetched=self._get_feeds_fetched() + 1)

                # Delay between feeds
                await asyncio.sleep(self.settings.fetch_delay_ms / 1000)

            # Fetch Wallabag articles (separate from RSS pipeline)
            wallabag_articles: list[ExtractedArticle] = []
            wallabag_entry_ids: list[int] = []
            with Session(engine) as wb_session:
                wallabag_service = WallabagService.from_db_or_settings(wb_session, self.settings)

            if wallabag_service.is_configured:
                try:
                    wb_raw = await wallabag_service.fetch_unread_articles()
                    digest_logger.info(
                        f"Wallabag: fetched {len(wb_raw)} unread articles",
                        component="feeds",
                        event="wallabag_fetched",
                        context={"count": len(wb_raw)},
                    )
                    for wb in wb_raw:
                        guid = f"wallabag-{wb['id']}"
                        if not await self._is_seen_wallabag(guid):
                            content = wb["content"] or ""
                            # Strip HTML for plain text
                            import re
                            plain = re.sub(r"<[^>]+>", "", content)
                            word_count = ContentProcessor.count_words(plain)

                            wallabag_articles.append(ExtractedArticle(
                                guid=guid,
                                url=wb["url"],
                                title=wb["title"],
                                content=plain,
                                author=wb.get("domain_name"),
                                word_count=word_count,
                                is_summary=False,
                                ai_failed=False,
                                processing_ms=0,
                            ))
                            wallabag_entry_ids.append(wb["id"])
                            await self._mark_seen_wallabag(guid, wb["url"], wb["title"])
                except Exception as e:
                    logger.warning(f"Wallabag fetch failed, continuing with RSS only: {e!r}", exc_info=True)
                    digest_logger.error(
                        f"Wallabag fetch failed: {e!r}",
                        component="feeds",
                        event="wallabag_failed",
                        context={"error": repr(e)},
                    )

            # Fetch newsletter emails from Gmail
            newsletter_articles: list[ExtractedArticle] = []
            newsletter_message_ids: list[str] = []
            newsletter_service = NewsletterService(self.settings)

            if newsletter_service.is_configured:
                try:
                    # Get message IDs before fetching (for mark_processed later)
                    newsletter_message_ids = await newsletter_service.get_fetched_message_ids()
                    nl_raw = await newsletter_service.fetch_newsletters()
                    digest_logger.info(
                        f"Newsletters: fetched {len(nl_raw)} emails",
                        component="feeds",
                        event="newsletters_fetched",
                        context={"count": len(nl_raw)},
                    )
                    for nl in nl_raw:
                        if not await self._is_seen_wallabag(nl.guid):
                            newsletter_articles.append(nl)
                            await self._mark_seen_wallabag(nl.guid, nl.url, nl.title)
                except Exception as e:
                    logger.warning(f"Newsletter fetch failed, continuing without: {e}")
                    digest_logger.error(
                        f"Newsletter fetch failed: {e}",
                        component="feeds",
                        event="newsletters_failed",
                        context={"error": str(e)},
                    )

            if not all_articles and not wallabag_articles and not newsletter_articles:
                logger.warning("No new articles found")
                digest_logger.pipeline_no_articles(str(self.digest_id), "No new articles found across all feeds")
                await self._complete(0)
                return

            # Cap total articles
            original_count = len(all_articles)
            all_articles = all_articles[: self.settings.max_articles_per_digest]
            if len(all_articles) < original_count:
                digest_logger.info(
                    f"Capped articles from {original_count} to {len(all_articles)} (max_articles_per_digest)",
                    component="pipeline",
                    event="capped",
                    context={"original": original_count, "capped": len(all_articles)},
                )
            await self._update_progress(total_articles=len(all_articles))

            # Stage 2 & 3: Extract and enrich
            await self._update_stage("extracting")
            digest_logger.pipeline_stage(
                "extracting",
                str(self.digest_id),
                articles_to_process=len(all_articles),
            )
            extracted_articles = []

            for article_data in all_articles:
                feed, parsed_article = article_data
                article_start = time.time()

                content = await self.content_processor.extract_content(parsed_article.url)
                if not content:
                    logger.warning(f"Could not extract: {parsed_article.url}")
                    digest_logger.article_extraction_failed(parsed_article.url, "Content extraction returned empty")
                    continue

                original_word_count = ContentProcessor.count_words(content)
                word_count = original_word_count

                # Enrich with AI if enabled
                is_summary = False
                ai_failed = False

                if feed.mode == "summarize":
                    await self._update_stage("enriching")
                    summary_content, ai_failed = await self.llm_service.summarize(content)
                    if not ai_failed:
                        content = summary_content
                        is_summary = True
                        word_count = ContentProcessor.count_words(content)
                        digest_logger.article_summarized(
                            parsed_article.title,
                            original_words=original_word_count,
                            summary_words=word_count,
                        )
                    else:
                        digest_logger.article_summarization_failed(
                            parsed_article.title,
                            "AI service returned error",
                            fallback=True,
                        )

                processing_ms = int((time.time() - article_start) * 1000)

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

                digest_logger.article_extracted(
                    parsed_article.title,
                    word_count=word_count,
                    url=parsed_article.url,
                )

                # Mark article as seen
                await self._mark_seen(feed.id, parsed_article)

                await self._update_progress(
                    articles_enriched=self._get_articles_enriched() + 1
                )

            # Enrich Wallabag articles with AI if configured
            if wallabag_articles and self.settings.wallabag_mode == "summarize":
                await self._update_stage("enriching")
                enriched_wallabag = []
                for article in wallabag_articles:
                    summary_content, ai_failed = await self.llm_service.summarize(article.content)
                    if not ai_failed:
                        enriched_wallabag.append(ExtractedArticle(
                            guid=article.guid,
                            url=article.url,
                            title=article.title,
                            content=summary_content,
                            author=article.author,
                            word_count=ContentProcessor.count_words(summary_content),
                            is_summary=True,
                            ai_failed=False,
                            processing_ms=article.processing_ms,
                        ))
                    else:
                        enriched_wallabag.append(article)
                wallabag_articles = enriched_wallabag

            if not extracted_articles and not wallabag_articles and not newsletter_articles:
                logger.warning("No articles extracted successfully")
                digest_logger.pipeline_no_articles(str(self.digest_id), "All article extractions failed")
                await self._complete(0)
                return

            # Stage 4: Compile EPUB
            await self._update_stage("compiling")
            total_count = len(extracted_articles) + len(wallabag_articles) + len(newsletter_articles)
            digest_logger.epub_generation_started(str(self.digest_id), total_count)

            # Get just the articles for EPUB generation
            articles_for_epub = [a for _, a in extracted_articles]

            epub_path = self.epub_generator.generate(
                articles_for_epub,
                period=period,
                saved_articles=wallabag_articles if wallabag_articles else None,
                newsletter_articles=newsletter_articles if newsletter_articles else None,
            )

            # Log EPUB file size
            try:
                file_size_kb = os.path.getsize(epub_path) // 1024
                digest_logger.epub_generation_completed(str(self.digest_id), epub_path, file_size_kb)
            except OSError:
                file_size_kb = 0

            # Save DigestArticle records
            await self._save_article_records(extracted_articles)

            # Save Wallabag article records
            if wallabag_articles:
                await self._save_wallabag_article_records(wallabag_articles, len(extracted_articles))

            # Save newsletter article records
            if newsletter_articles:
                await self._save_newsletter_article_records(
                    newsletter_articles, len(extracted_articles) + len(wallabag_articles)
                )

            # Mark newsletter emails as read
            if newsletter_service.is_configured and newsletter_message_ids:
                try:
                    await newsletter_service.mark_processed(newsletter_message_ids)
                except Exception:
                    logger.warning("Failed to mark newsletter emails as read")

            # Mark Wallabag entries as processed
            if wallabag_service.is_configured and wallabag_entry_ids:
                for entry_id in wallabag_entry_ids:
                    try:
                        await wallabag_service.mark_processed(entry_id)
                    except Exception:
                        logger.warning(f"Failed to mark wallabag entry {entry_id} as processed")

            await self._complete(
                len(extracted_articles) + len(wallabag_articles) + len(newsletter_articles),
                epub_path,
            )

        except Exception as e:
            logger.exception(f"Pipeline failed: {e}")
            # Get current stage for error context
            current_stage = None
            with Session(engine) as session:
                digest = session.get(Digest, self.digest_id)
                if digest:
                    current_stage = digest.stage
            digest_logger.pipeline_failed(str(self.digest_id), str(e), stage=current_stage)
            await self._fail(str(e))
            raise

    async def _get_active_feeds(self) -> list[Feed]:
        """Get all active feeds."""
        with Session(engine) as session:
            statement = select(Feed).where(Feed.is_active == True)
            return list(session.exec(statement).all())

    async def _fetch_feed(self, feed: Feed) -> tuple[list[tuple[Feed, any]], int]:
        """
        Fetch and filter articles from a feed.

        Args:
            feed: The feed to process.

        Returns:
            Tuple of (list of (feed, parsed_article) tuples, total article count).
        """
        parsed = await self.content_processor.parse_feed(feed.url)
        total_count = len(parsed)

        # Filter out already seen articles
        new_articles = []
        for article in parsed:
            if not await self._is_seen(feed.id, article.guid):
                new_articles.append((feed, article))

        logger.info(
            f"Feed {feed.title}: {total_count} total, {len(new_articles)} new"
        )
        return new_articles, total_count

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

    async def _is_seen_wallabag(self, guid: str) -> bool:
        """Check if a Wallabag article has been seen recently."""
        cutoff = datetime.utcnow() - timedelta(
            days=self.settings.seen_article_retention_days
        )
        with Session(engine) as session:
            statement = (
                select(SeenArticle)
                .where(SeenArticle.feed_id == None)  # noqa: E711
                .where(SeenArticle.guid == guid)
                .where(SeenArticle.seen_at > cutoff)
            )
            return session.exec(statement).first() is not None

    async def _mark_seen_wallabag(self, guid: str, url: str, title: str) -> None:
        """Mark a Wallabag article as seen."""
        with Session(engine) as session:
            seen = SeenArticle(
                feed_id=None,
                guid=guid,
                url=url,
                title=title,
            )
            session.add(seen)
            session.commit()

    async def _save_wallabag_article_records(
        self, articles: list[ExtractedArticle], offset: int
    ) -> None:
        """Save DigestArticle records for Wallabag articles."""
        with Session(engine) as session:
            for sort_order, article in enumerate(articles, offset):
                record = DigestArticle(
                    digest_id=self.digest_id,
                    feed_id=None,
                    title=article.title,
                    url=article.url,
                    mode="summarized" if article.is_summary else "raw",
                    word_count=article.word_count,
                    ai_failed=article.ai_failed,
                    processing_ms=article.processing_ms,
                    content=article.content,
                    author=article.author,
                    feed_title="Wallabag",
                    sort_order=sort_order,
                )
                session.add(record)
            session.commit()

    async def _save_newsletter_article_records(
        self, articles: list[ExtractedArticle], offset: int
    ) -> None:
        """Save DigestArticle records for newsletter articles."""
        with Session(engine) as session:
            for sort_order, article in enumerate(articles, offset):
                record = DigestArticle(
                    digest_id=self.digest_id,
                    feed_id=None,
                    title=article.title,
                    url=article.url,
                    mode="raw",
                    word_count=article.word_count,
                    ai_failed=False,
                    processing_ms=article.processing_ms,
                    content=article.content,
                    author=article.author,
                    feed_title="Newsletter",
                    sort_order=sort_order,
                )
                session.add(record)
            session.commit()

    async def _save_article_records(
        self, articles: list[tuple[Feed, ExtractedArticle]]
    ) -> None:
        """Save DigestArticle records for audit trail and client syncing."""
        with Session(engine) as session:
            for sort_order, (feed, article) in enumerate(articles):
                record = DigestArticle(
                    digest_id=self.digest_id,
                    feed_id=feed.id,
                    title=article.title,
                    url=article.url,
                    mode="summarized" if article.is_summary else "raw",
                    word_count=article.word_count,
                    ai_failed=article.ai_failed,
                    processing_ms=article.processing_ms,
                    # Article content for client syncing
                    content=article.content,
                    author=article.author,
                    feed_title=feed.title,
                    sort_order=sort_order,
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
        duration = time.time() - self.start_time if self.start_time else 0

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

        digest_logger.pipeline_completed(
            str(self.digest_id),
            article_count=article_count,
            duration_seconds=duration,
            epub_path=epub_path,
        )

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
