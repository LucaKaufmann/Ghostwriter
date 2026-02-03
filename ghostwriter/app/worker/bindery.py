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
from app.models.client_config import ClientConfig
from app.models.feed import Feed
from app.models.seen_article import SeenArticle
from app.services.content_processor import ContentProcessor, ExtractedArticle
from app.services.epub_generator import EpubGenerator
from app.services.llm_service import LLMService
from app.services.summarize_sh_service import SummarizeShService
from app.services.newsletter_service import NewsletterService
from app.services.wallabag_service import WallabagService

logger = logging.getLogger(__name__)

# Well-known synthetic feed URLs for non-RSS sources
_SYNTHETIC_FEED_URLS = {
    "wallabag": "synthetic://wallabag",
    "newsletter": "synthetic://newsletter",
}


def get_or_create_synthetic_feed(session: Session, source: str) -> Feed:
    """Get or create a synthetic Feed row for non-RSS sources (Wallabag, Newsletter)."""
    url = _SYNTHETIC_FEED_URLS[source]
    statement = select(Feed).where(Feed.url == url)
    feed = session.exec(statement).first()
    if feed is None:
        feed = Feed(
            url=url,
            title=source.capitalize(),
            is_active=False,  # Not a real RSS feed; never fetched
            mode="raw",
            max_articles=0,
        )
        session.add(feed)
        session.commit()
        session.refresh(feed)
        logger.info(f"Created synthetic feed for {source}: {feed.id}")
    return feed


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
        self.summarize_sh_service = SummarizeShService(self.settings)
        self.epub_generator = EpubGenerator(self.settings)
        self.start_time: float | None = None

        # In-memory progress counters (avoid per-article DB reads)
        self._feeds_fetched: int = 0
        self._articles_enriched: int = 0
        self._progress_dirty: bool = False

        # Synthetic feed IDs for non-RSS sources (resolved lazily)
        self._wallabag_feed_id: UUID | None = None
        self._newsletter_feed_id: UUID | None = None

    def _get_synthetic_feed_id(self, source: str) -> UUID:
        """Get the synthetic feed ID, creating the feed row if needed."""
        attr = f"_{source}_feed_id"
        fid = getattr(self, attr)
        if fid is None:
            with Session(engine) as session:
                feed = get_or_create_synthetic_feed(session, source)
                fid = feed.id
                setattr(self, attr, fid)
        return fid

    def _ensure_synthetic_feeds(self) -> None:
        """Pre-create synthetic feeds at pipeline start so they're always available."""
        for source in _SYNTHETIC_FEED_URLS:
            self._get_synthetic_feed_id(source)

    async def run(self) -> None:
        """Execute the full pipeline."""
        self.start_time = time.time()

        # Pre-create synthetic feeds so feed_id is always available
        self._ensure_synthetic_feeds()

        # Get digest info for logging and current client config
        summarize_sh_enabled = False
        with Session(engine) as session:
            digest = session.get(Digest, self.digest_id)
            period = digest.period if digest else "manual"
            client_config = session.exec(select(ClientConfig)).first()
            if client_config:
                summarize_sh_enabled = client_config.summarize_sh_enabled

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

            # Stage 1: Fetch all feeds (parallel with semaphore)
            fetch_sem = asyncio.Semaphore(self.settings.max_concurrent_fetches)
            all_articles: list[tuple[Feed, any]] = []
            articles_lock = asyncio.Lock()

            async def _fetch_one(feed: Feed) -> None:
                async with fetch_sem:
                    feed_start = time.time()
                    digest_logger.feed_fetch_started(feed.title, feed.url)

                    try:
                        articles, total_in_feed = await self._fetch_feed(feed)
                        async with articles_lock:
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

                    self._feeds_fetched += 1
                    self._progress_dirty = True
                    await self._flush_progress_if_needed()

                    # Per-fetch delay (inside semaphore to rate-limit)
                    await asyncio.sleep(self.settings.fetch_delay_ms / 1000)

            logger.info(f"Fetching {len(feeds)} feeds with concurrency={self.settings.max_concurrent_fetches}")
            await asyncio.gather(*[_fetch_one(f) for f in feeds])
            await self._flush_progress_if_needed(force=True)

            # Fetch Wallabag articles (separate from RSS pipeline)
            wallabag_articles: list[ExtractedArticle] = []
            wallabag_entry_ids: list[int] = []
            wallabag_enabled = False
            with Session(engine) as wb_session:
                wallabag_service = WallabagService.from_db_or_settings(wb_session, self.settings)
                from app.models.wallabag_config import WallabagConfig
                wb_cfg = wb_session.exec(select(WallabagConfig)).first()
                wallabag_enabled = wb_cfg.enabled if wb_cfg else True

            if wallabag_service.is_configured and wallabag_enabled:
                try:
                    wb_raw = await wallabag_service.fetch_unread_articles()
                    digest_logger.info(
                        f"Wallabag: fetched {len(wb_raw)} unread articles",
                        component="feeds",
                        event="wallabag_fetched",
                        context={"count": len(wb_raw)},
                    )
                    wb_feed_id = self._get_synthetic_feed_id("wallabag")
                    for wb in wb_raw:
                        guid = f"wallabag-{wb['id']}"
                        if not await self._is_seen(wb_feed_id, guid):
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
                            await self._mark_seen_raw(wb_feed_id, guid, wb["url"], wb["title"])
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

            newsletters_enabled = True
            with Session(engine) as nl_session:
                from app.models.client_config import ClientConfig
                nl_config = nl_session.exec(select(ClientConfig)).first()
                if nl_config:
                    newsletters_enabled = nl_config.newsletters_enabled

            if newsletter_service.is_configured and newsletters_enabled:
                try:
                    # Single fetch returns both articles and their message IDs in sync
                    nl_raw, newsletter_message_ids = await newsletter_service.fetch_newsletters()
                    digest_logger.info(
                        f"Newsletters: fetched {len(nl_raw)} emails",
                        component="feeds",
                        event="newsletters_fetched",
                        context={"count": len(nl_raw)},
                    )
                    nl_feed_id = self._get_synthetic_feed_id("newsletter")
                    for nl in nl_raw:
                        if not await self._is_seen(nl_feed_id, nl.guid):
                            newsletter_articles.append(nl)
                            await self._mark_seen_raw(nl_feed_id, nl.guid, nl.url, nl.title)
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

            # Stage 2 & 3: Extract and enrich (parallel with semaphore)
            await self._update_stage("extracting")
            digest_logger.pipeline_stage(
                "extracting",
                str(self.digest_id),
                articles_to_process=len(all_articles),
            )
            extracted_articles: list[tuple[Feed, ExtractedArticle]] = []
            extracted_lock = asyncio.Lock()
            extract_sem = asyncio.Semaphore(5)

            async def _extract_one(feed: Feed, parsed_article) -> None:
                async with extract_sem:
                    article_start = time.time()

                    content = None
                    original_word_count = 0
                    word_count = 0
                    is_summary = False
                    ai_failed = False

                    if feed.mode == "summarize" and summarize_sh_enabled:
                        summarize_result = await self.summarize_sh_service.summarize_url(
                            parsed_article.url
                        )
                        if not summarize_result.ai_failed and summarize_result.summary:
                            content = summarize_result.summary
                            is_summary = True
                            word_count = ContentProcessor.count_words(content)
                            original_word_count = (
                                summarize_result.original_word_count or word_count
                            )
                            digest_logger.article_summarized(
                                parsed_article.title,
                                original_words=original_word_count,
                                summary_words=word_count,
                            )
                        else:
                            ai_failed = True
                            digest_logger.article_summarization_failed(
                                parsed_article.title,
                                "Summarize.sh returned error",
                                fallback=True,
                            )

                    if content is None:
                        content = await self.content_processor.extract_content(
                            parsed_article.url
                        )
                        if not content:
                            logger.warning(f"Could not extract: {parsed_article.url}")
                            digest_logger.article_extraction_failed(
                                parsed_article.url,
                                "Content extraction returned empty",
                            )
                            return

                        original_word_count = ContentProcessor.count_words(content)
                        word_count = original_word_count

                        # Enrich with AI if enabled (fallback path)
                        if (
                            feed.mode == "summarize"
                            and not summarize_sh_enabled
                        ):
                            summary_content, ai_failed = await self.llm_service.summarize(
                                content
                            )
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
                    async with extracted_lock:
                        extracted_articles.append((feed, extracted))

                    digest_logger.article_extracted(
                        parsed_article.title,
                        word_count=word_count,
                        url=parsed_article.url,
                    )

                    await self._mark_seen(feed.id, parsed_article)

                    self._articles_enriched += 1
                    self._progress_dirty = True
                    await self._flush_progress_if_needed()

            logger.info(f"Extracting {len(all_articles)} articles with concurrency=5")
            await asyncio.gather(*[_extract_one(feed, art) for feed, art in all_articles])
            await self._flush_progress_if_needed(force=True)

            # Enrich Wallabag articles with AI if configured (parallel)
            if wallabag_articles and self.settings.wallabag_mode == "summarize":
                await self._update_stage("enriching")
                llm_sem = asyncio.Semaphore(3)
                enriched_wallabag: list[ExtractedArticle] = []
                wb_lock = asyncio.Lock()

                async def _summarize_wb(article: ExtractedArticle) -> None:
                    async with llm_sem:
                        summary_content, ai_failed = await self.llm_service.summarize(article.content)
                        if not ai_failed:
                            result = ExtractedArticle(
                                guid=article.guid,
                                url=article.url,
                                title=article.title,
                                content=summary_content,
                                author=article.author,
                                word_count=ContentProcessor.count_words(summary_content),
                                is_summary=True,
                                ai_failed=False,
                                processing_ms=article.processing_ms,
                            )
                        else:
                            result = article
                    async with wb_lock:
                        enriched_wallabag.append(result)

                logger.info(f"Summarizing {len(wallabag_articles)} Wallabag articles with concurrency=3")
                await asyncio.gather(*[_summarize_wb(a) for a in wallabag_articles])
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

            # Mark Wallabag entries as processed (parallel)
            if wallabag_service.is_configured and wallabag_entry_ids:
                wb_sem = asyncio.Semaphore(5)

                async def _mark_wb(eid: int) -> None:
                    async with wb_sem:
                        try:
                            await wallabag_service.mark_processed(eid)
                        except Exception:
                            logger.warning(f"Failed to mark wallabag entry {eid} as processed")

                await asyncio.gather(*[_mark_wb(eid) for eid in wallabag_entry_ids])

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

    async def _mark_seen_raw(self, feed_id: UUID, guid: str, url: str, title: str) -> None:
        """Mark an article as seen using raw fields (for non-RSS sources)."""
        with Session(engine) as session:
            seen = SeenArticle(
                feed_id=feed_id,
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
                    feed_id=self._get_synthetic_feed_id("wallabag"),
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
                    feed_id=self._get_synthetic_feed_id("newsletter"),
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

    async def _flush_progress_if_needed(self, force: bool = False) -> None:
        """Flush in-memory progress counters to DB periodically (every 5 updates) or when forced."""
        if not self._progress_dirty and not force:
            return
        total = self._feeds_fetched + self._articles_enriched
        if force or total % 5 == 0:
            await self._update_progress(
                feeds_fetched=self._feeds_fetched,
                articles_enriched=self._articles_enriched,
            )
            self._progress_dirty = False

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
