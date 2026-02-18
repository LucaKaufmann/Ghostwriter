"""Media Processing Pipeline - Decoupled podcast/YouTube transcription worker."""

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlmodel import Session, select

from app.core.config import get_settings
from app.core.database import engine
from app.core.logging import digest_logger
from app.models.client_config import ClientConfig
from app.models.media_feed import MediaFeed
from app.models.media_item import MediaItem
from app.models.media_processing_run import MediaProcessingRun
from app.services.content_processor import ContentProcessor
from app.services.llm_service import LLMService
from app.services.media_processor import MediaProcessor

logger = logging.getLogger(__name__)

# Stale "processing" timeout — if an item has been "processing" longer than this,
# consider it abandoned and allow the pipeline to re-process it.
_STALE_PROCESSING_TIMEOUT = timedelta(minutes=90)


async def run_media_pipeline() -> None:
    """
    Main entry point for the media processing pipeline.

    Stages:
    1. Fetch — parse all active media_feeds
    2. Dedup — filter items already in media_items
    3. Create — insert new pending items
    4. Process — transcribe/summarize each pending item sequentially
    """
    settings = get_settings()

    # Check for stuck "processing" items (stale lock)
    _release_stale_processing_items()

    # Check if any items are currently processing (skip run if so)
    with Session(engine) as session:
        processing_count = session.exec(
            select(MediaItem).where(MediaItem.status == "processing")
        ).first()
        if processing_count:
            logger.info("Media pipeline: items still processing, skipping this run")
            return

    logger.info("Media pipeline: starting run")
    digest_logger.info(
        "Media processing pipeline started",
        component="media_pipeline",
        event="started",
    )

    # Create a run record
    run = MediaProcessingRun(status="running")
    with Session(engine) as session:
        session.add(run)
        session.commit()
        session.refresh(run)
        run_id = run.id

    run_start = time.time()

    try:
        # Stage 1 & 2: Fetch feeds and create pending items
        new_items_count = await _fetch_and_create_items(settings)

        # Update run with discovered items
        _update_run(run_id, items_discovered=new_items_count)

        # Stage 3: Process pending items sequentially
        processed_count, failed_count = await _process_pending_items(settings)

        duration_ms = int((time.time() - run_start) * 1000)

        # Finalize run as completed
        _update_run(
            run_id,
            status="completed",
            completed_at=datetime.now(timezone.utc),
            duration_ms=duration_ms,
            items_processed=processed_count,
            items_failed=failed_count,
        )

        logger.info(
            f"Media pipeline: completed. New items: {new_items_count}, Processed: {processed_count}"
        )
        digest_logger.info(
            f"Media processing pipeline completed: {new_items_count} new, {processed_count} processed",
            component="media_pipeline",
            event="completed",
            context={"new_items": new_items_count, "processed": processed_count},
        )
    except Exception as e:
        duration_ms = int((time.time() - run_start) * 1000)
        _update_run(
            run_id,
            status="failed",
            completed_at=datetime.now(timezone.utc),
            duration_ms=duration_ms,
            error_message=str(e)[:500],
        )
        logger.exception(f"Media pipeline failed: {e}")
        digest_logger.error(
            f"Media processing pipeline failed: {e}",
            component="media_pipeline",
            event="failed",
            context={"error": str(e)},
        )


def _update_run(run_id: UUID, **kwargs) -> None:
    """Update fields on a MediaProcessingRun."""
    with Session(engine) as session:
        run = session.get(MediaProcessingRun, run_id)
        if run:
            for key, value in kwargs.items():
                setattr(run, key, value)
            session.add(run)
            session.commit()


def _release_stale_processing_items() -> None:
    """Release items stuck in 'processing' state past the timeout."""
    cutoff = datetime.now(timezone.utc) - _STALE_PROCESSING_TIMEOUT
    with Session(engine) as session:
        stale_items = session.exec(
            select(MediaItem)
            .where(MediaItem.status == "processing")
            .where(MediaItem.created_at < cutoff)
        ).all()
        for item in stale_items:
            logger.warning(f"Releasing stale processing item: {item.id} ({item.title})")
            item.status = "failed"
            item.error_message = "Processing timed out (stale lock released)"
            session.add(item)
        if stale_items:
            session.commit()


async def _fetch_and_create_items(settings) -> int:
    """Fetch all active media feeds and create pending items for new entries."""
    content_processor = ContentProcessor(settings)
    new_count = 0

    with Session(engine) as session:
        feeds = session.exec(
            select(MediaFeed)
            .where(MediaFeed.is_active == True)
            .where(MediaFeed.deleted_at == None)
        ).all()

    if not feeds:
        logger.info("Media pipeline: no active media feeds")
        return 0

    for feed in feeds:
        try:
            feed_url = feed.resolved_feed_url or feed.url
            parsed_articles = await content_processor.parse_feed(
                feed_url, max_entries=feed.max_items
            )

            with Session(engine) as session:
                # Get existing GUIDs for this feed to dedup
                existing_guids = set(
                    session.exec(
                        select(MediaItem.guid)
                        .where(MediaItem.media_feed_id == feed.id)
                    ).all()
                )

                for article in parsed_articles:
                    if article.guid in existing_guids:
                        continue

                    item = MediaItem(
                        media_feed_id=feed.id,
                        guid=article.guid,
                        url=article.url,
                        content_url=article.content_url,
                        title=article.title,
                        author=article.author,
                        content_type=feed.feed_type,
                        mode=feed.mode,
                        status="pending",
                    )
                    session.add(item)
                    new_count += 1

                session.commit()

            logger.info(
                f"Media feed '{feed.title}': {len(parsed_articles)} total, "
                f"{len(parsed_articles) - len(existing_guids & {a.guid for a in parsed_articles})} new"
            )
        except Exception as e:
            logger.warning(f"Failed to fetch media feed '{feed.title}': {e}")
            digest_logger.error(
                f"Media feed fetch failed: {feed.title}",
                component="media_pipeline",
                event="feed_fetch_failed",
                context={"feed": feed.title, "error": str(e)},
            )

    return new_count


async def _process_pending_items(settings) -> tuple[int, int]:
    """Process all pending media items sequentially. Returns (processed, failed) counts."""
    media_processor = MediaProcessor(settings)
    llm_service = LLMService(settings)
    processed_count = 0
    failed_count = 0

    # Load whisper config
    with Session(engine) as session:
        client_config = session.exec(select(ClientConfig)).first()
        whisper_provider = client_config.whisper_provider if client_config else "local"
        whisper_model = client_config.whisper_model if client_config else "base.en"
        whisper_timeout = (
            client_config.whisper_timeout_minutes * 60 if client_config else 1800
        )
        whisper_timeout_minutes = (
            client_config.whisper_timeout_minutes if client_config else 30
        )

    while True:
        # Fetch next pending item
        with Session(engine) as session:
            item = session.exec(
                select(MediaItem)
                .where(MediaItem.status == "pending")
                .order_by(MediaItem.created_at)
            ).first()

            if not item:
                break

            # Mark as processing
            item.status = "processing"
            # created_at doubles as processing start for stale-lock detection.
            item.created_at = datetime.now(timezone.utc)
            session.add(item)
            session.commit()

            # Detach values we need
            item_id = item.id
            item_url = item.url
            item_content_url = item.content_url
            item_title = item.title
            item_author = item.author
            item_mode = item.mode
            item_content_type = item.content_type

        start_time = time.time()
        logger.info(f"Processing media item: {item_title} ({item_url})")

        try:
            # Transcribe
            result = await media_processor.process(
                item_url,
                content_url=item_content_url,
                whisper_provider=whisper_provider,
                whisper_model=whisper_model,
                timeout_seconds=whisper_timeout,
            )

            if not result.is_media:
                _update_item_failed(item_id, "URL is not a media source", start_time)
                failed_count += 1
                continue

            if result.error or not result.text:
                error_msg = result.error or "Transcription returned empty"
                error_msg = _enrich_timeout_error(error_msg, whisper_timeout_minutes)
                _update_item_failed(item_id, error_msg, start_time)
                failed_count += 1
                continue

            content = result.text
            is_summary = False
            ai_failed = False

            # Summarize if mode is "summarize"
            if item_mode == "summarize":
                summary_content, ai_failed = await llm_service.summarize(
                    content,
                    title=item_title,
                    url=item_url,
                    author=item_author,
                    source=item_content_type.capitalize(),
                    content_type="transcript",
                )
                if not ai_failed:
                    content = summary_content
                    is_summary = True

            processing_ms = int((time.time() - start_time) * 1000)
            word_count = ContentProcessor.count_words(content)

            # Update item as completed
            with Session(engine) as session:
                item = session.get(MediaItem, item_id)
                if item:
                    item.content = content
                    item.word_count = word_count
                    item.is_summary = is_summary
                    item.ai_failed = ai_failed
                    item.processing_ms = processing_ms
                    item.status = "completed"
                    item.completed_at = datetime.now(timezone.utc)
                    session.add(item)
                    session.commit()

            processed_count += 1
            logger.info(
                f"Completed media item: {item_title} ({word_count} words, {processing_ms}ms)"
            )
            digest_logger.info(
                f"Media item processed: {item_title}",
                component="media_pipeline",
                event="item_completed",
                context={
                    "title": item_title,
                    "word_count": word_count,
                    "processing_ms": processing_ms,
                    "is_summary": is_summary,
                },
            )

        except Exception as e:
            error_msg = _enrich_timeout_error(str(e)[:500], whisper_timeout_minutes)
            logger.exception(f"Failed to process media item: {item_title}")
            _update_item_failed(item_id, error_msg, start_time)
            failed_count += 1

    return processed_count, failed_count


def _enrich_timeout_error(error: str, timeout_minutes: int) -> str:
    """Append actionable context to timeout errors."""
    if "timed out" in error.lower():
        return (
            f"{error} (current timeout: {timeout_minutes}m — "
            f"you can increase this in Settings > Media Processing)"
        )
    return error


def _update_item_failed(item_id: UUID, error: str, start_time: float) -> None:
    """Mark a media item as failed."""
    processing_ms = int((time.time() - start_time) * 1000)
    with Session(engine) as session:
        item = session.get(MediaItem, item_id)
        if item:
            item.status = "failed"
            item.error_message = error
            item.processing_ms = processing_ms
            session.add(item)
            session.commit()
    logger.warning(f"Media item failed: {item_id} - {error}")
