"""
Structured logging for Ghostwriter digest activity.

Provides daily rotating log files optimized for debugging and AI analysis.
Logs are written in a structured format that's both human-readable and
easy for AI agents to parse and understand.

Log files are stored in /app/logs (configurable via LOGS_DIR) with one
file per day named ghostwriter-YYYY-MM-DD.log.
"""

import json
import logging
import os
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from typing import Any

from app.core.config import get_settings


class DigestActivityFormatter(logging.Formatter):
    """
    Custom formatter that produces structured, AI-friendly log entries.

    Each log entry includes:
    - ISO timestamp
    - Log level
    - Component (scheduler, pipeline, feeds, etc.)
    - Event type (for categorization)
    - Human-readable message
    - Structured context data (as JSON when present)
    """

    def format(self, record: logging.LogRecord) -> str:
        # Build the base message
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        level = record.levelname

        # Extract component and event from record if set
        component = getattr(record, 'component', record.name.split('.')[-1])
        event = getattr(record, 'event', 'log')

        # Build structured line
        parts = [
            f"[{timestamp}]",
            f"[{level}]",
            f"[{component}]",
            f"[{event}]",
            record.getMessage(),
        ]

        # Add context data if present
        context = getattr(record, 'context', None)
        if context:
            parts.append(f"\n  Context: {json.dumps(context, indent=2, default=str)}")

        # Add exception info if present
        if record.exc_info:
            parts.append(f"\n  Exception: {self.formatException(record.exc_info)}")

        return " ".join(parts[:5]) + ("".join(parts[5:]) if len(parts) > 5 else "")


class DigestActivityLogger:
    """
    Specialized logger for digest-related activity.

    Provides structured logging methods that capture context about:
    - Schedule events (triggers, updates, skips)
    - Pipeline stages (fetch, extract, enrich, compile)
    - Feed processing (success, failure, article counts)
    - Digest completion (statistics, timing)

    Usage:
        from app.core.logging import digest_logger

        digest_logger.schedule_triggered("morning", digest_id="abc-123")
        digest_logger.pipeline_stage("fetching", digest_id="abc-123", feeds_total=5)
        digest_logger.feed_processed("Tech News", articles_found=3, new_articles=2)
        digest_logger.digest_completed(digest_id="abc-123", article_count=15, duration_seconds=45)
    """

    def __init__(self):
        self.logger = logging.getLogger("ghostwriter.digest")
        self._configured = False

    def configure(self, logs_dir: str | None = None) -> None:
        """
        Configure the digest activity logger with file output.

        Args:
            logs_dir: Directory for log files. Defaults to settings.logs_dir.
        """
        if self._configured:
            return

        settings = get_settings()
        logs_dir = logs_dir or getattr(settings, 'logs_dir', '/app/logs')

        # Ensure logs directory exists
        os.makedirs(logs_dir, exist_ok=True)

        # Create daily rotating file handler
        log_file = os.path.join(logs_dir, "ghostwriter.log")
        handler = TimedRotatingFileHandler(
            log_file,
            when="midnight",
            interval=1,
            backupCount=30,  # Keep 30 days of logs
            utc=True,
        )
        handler.suffix = "%Y-%m-%d"
        handler.namer = lambda name: name.replace(".log.", "-") + ".log"

        # Set our custom formatter
        handler.setFormatter(DigestActivityFormatter())

        # Configure logger
        self.logger.setLevel(logging.DEBUG)
        self.logger.addHandler(handler)

        # Don't propagate to root logger (avoid duplicate console output)
        self.logger.propagate = False

        self._configured = True
        self.info("Digest activity logging initialized", component="logging", event="startup")

    def _log(
        self,
        level: int,
        message: str,
        component: str = "general",
        event: str = "log",
        context: dict[str, Any] | None = None,
        exc_info: bool = False,
    ) -> None:
        """Internal log method with structured fields."""
        extra = {
            'component': component,
            'event': event,
            'context': context,
        }
        self.logger.log(level, message, extra=extra, exc_info=exc_info)

    def debug(self, message: str, **kwargs) -> None:
        self._log(logging.DEBUG, message, **kwargs)

    def info(self, message: str, **kwargs) -> None:
        self._log(logging.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs) -> None:
        self._log(logging.WARNING, message, **kwargs)

    def error(self, message: str, exc_info: bool = False, **kwargs) -> None:
        self._log(logging.ERROR, message, exc_info=exc_info, **kwargs)

    # ===== Schedule Events =====

    def schedule_startup(self, schedules: list[dict]) -> None:
        """Log scheduler initialization with configured schedules."""
        self.info(
            f"Scheduler initialized with {len(schedules)} schedules",
            component="scheduler",
            event="startup",
            context={"schedules": schedules},
        )

    def schedule_triggered(self, period: str, digest_id: str | None = None) -> None:
        """Log when a scheduled digest run is triggered."""
        self.info(
            f"Scheduled {period} digest triggered",
            component="scheduler",
            event="triggered",
            context={"period": period, "digest_id": digest_id},
        )

    def schedule_skipped(self, period: str, reason: str) -> None:
        """Log when a scheduled run is skipped."""
        self.warning(
            f"Scheduled {period} digest skipped: {reason}",
            component="scheduler",
            event="skipped",
            context={"period": period, "reason": reason},
        )

    def schedule_updated(self, period: str, hour: int, minute: int, enabled: bool, timezone: str) -> None:
        """Log when a schedule is updated."""
        self.info(
            f"Schedule updated: {period} at {hour:02d}:{minute:02d} ({timezone}), enabled={enabled}",
            component="scheduler",
            event="updated",
            context={
                "period": period,
                "hour": hour,
                "minute": minute,
                "enabled": enabled,
                "timezone": timezone,
            },
        )

    def schedule_next_run(self, period: str, next_run: datetime | None) -> None:
        """Log the next scheduled run time."""
        if next_run:
            self.debug(
                f"Next {period} digest scheduled for {next_run.isoformat()}",
                component="scheduler",
                event="next_run",
                context={"period": period, "next_run": next_run.isoformat()},
            )

    # ===== Pipeline Events =====

    def pipeline_started(self, digest_id: str, period: str, trigger: str = "manual") -> None:
        """Log when a digest pipeline starts."""
        self.info(
            f"Digest pipeline started: {digest_id} ({period}, trigger={trigger})",
            component="pipeline",
            event="started",
            context={"digest_id": digest_id, "period": period, "trigger": trigger},
        )

    def pipeline_stage(self, stage: str, digest_id: str, **details) -> None:
        """Log pipeline stage transitions."""
        detail_str = ", ".join(f"{k}={v}" for k, v in details.items()) if details else ""
        self.info(
            f"Pipeline stage: {stage}" + (f" ({detail_str})" if detail_str else ""),
            component="pipeline",
            event="stage",
            context={"digest_id": digest_id, "stage": stage, **details},
        )

    def pipeline_completed(
        self,
        digest_id: str,
        article_count: int,
        duration_seconds: float,
        epub_path: str | None = None,
    ) -> None:
        """Log successful pipeline completion."""
        self.info(
            f"Digest completed: {article_count} articles in {duration_seconds:.1f}s",
            component="pipeline",
            event="completed",
            context={
                "digest_id": digest_id,
                "article_count": article_count,
                "duration_seconds": round(duration_seconds, 2),
                "epub_path": epub_path,
            },
        )

    def pipeline_failed(self, digest_id: str, error: str, stage: str | None = None) -> None:
        """Log pipeline failure."""
        self.error(
            f"Digest failed: {error}",
            component="pipeline",
            event="failed",
            context={"digest_id": digest_id, "error": error, "stage": stage},
            exc_info=True,
        )

    def pipeline_no_articles(self, digest_id: str, reason: str) -> None:
        """Log when pipeline completes with no articles."""
        self.warning(
            f"Digest completed with no articles: {reason}",
            component="pipeline",
            event="no_articles",
            context={"digest_id": digest_id, "reason": reason},
        )

    # ===== Feed Events =====

    def feed_fetch_started(self, feed_title: str, feed_url: str) -> None:
        """Log when a feed fetch begins."""
        self.debug(
            f"Fetching feed: {feed_title}",
            component="feeds",
            event="fetch_started",
            context={"feed_title": feed_title, "feed_url": feed_url},
        )

    def feed_fetch_completed(
        self,
        feed_title: str,
        total_articles: int,
        new_articles: int,
        fetch_time_ms: int,
    ) -> None:
        """Log feed fetch results."""
        self.info(
            f"Feed fetched: {feed_title} - {new_articles} new of {total_articles} total ({fetch_time_ms}ms)",
            component="feeds",
            event="fetch_completed",
            context={
                "feed_title": feed_title,
                "total_articles": total_articles,
                "new_articles": new_articles,
                "fetch_time_ms": fetch_time_ms,
            },
        )

    def feed_fetch_failed(self, feed_title: str, feed_url: str, error: str) -> None:
        """Log feed fetch failure."""
        self.error(
            f"Feed fetch failed: {feed_title} - {error}",
            component="feeds",
            event="fetch_failed",
            context={"feed_title": feed_title, "feed_url": feed_url, "error": error},
        )

    # ===== Article Events =====

    def article_extracted(self, article_title: str, word_count: int, url: str) -> None:
        """Log successful article extraction."""
        self.debug(
            f"Article extracted: {article_title[:50]}... ({word_count} words)",
            component="articles",
            event="extracted",
            context={"title": article_title, "word_count": word_count, "url": url},
        )

    def article_extraction_failed(self, url: str, error: str) -> None:
        """Log article extraction failure."""
        self.warning(
            f"Article extraction failed: {url} - {error}",
            component="articles",
            event="extraction_failed",
            context={"url": url, "error": error},
        )

    def article_summarized(self, article_title: str, original_words: int, summary_words: int) -> None:
        """Log successful AI summarization."""
        self.debug(
            f"Article summarized: {article_title[:50]}... ({original_words} -> {summary_words} words)",
            component="articles",
            event="summarized",
            context={
                "title": article_title,
                "original_words": original_words,
                "summary_words": summary_words,
            },
        )

    def article_summarization_failed(self, article_title: str, error: str, fallback: bool = True) -> None:
        """Log AI summarization failure."""
        action = "falling back to raw content" if fallback else "skipping article"
        self.warning(
            f"Summarization failed for '{article_title[:50]}...': {error}, {action}",
            component="articles",
            event="summarization_failed",
            context={"title": article_title, "error": error, "fallback": fallback},
        )

    # ===== EPUB Events =====

    def epub_generation_started(self, digest_id: str, article_count: int) -> None:
        """Log EPUB generation start."""
        self.info(
            f"Generating EPUB with {article_count} articles",
            component="epub",
            event="started",
            context={"digest_id": digest_id, "article_count": article_count},
        )

    def epub_generation_completed(self, digest_id: str, file_path: str, file_size_kb: int) -> None:
        """Log EPUB generation completion."""
        self.info(
            f"EPUB generated: {file_path} ({file_size_kb} KB)",
            component="epub",
            event="completed",
            context={"digest_id": digest_id, "file_path": file_path, "file_size_kb": file_size_kb},
        )

    # ===== Client Sync Events =====

    def sync_heartbeat(self, schedules_active: bool, reactivated: bool = False) -> None:
        """Log client heartbeat received."""
        msg = "Client heartbeat received"
        if reactivated:
            msg += " (schedules reactivated)"
        self.info(
            msg,
            component="sync",
            event="heartbeat",
            context={"schedules_active": schedules_active, "reactivated": reactivated},
        )

    def sync_feed_push(
        self,
        feed_count: int,
        created: int,
        updated: int,
        unchanged: int,
        duration_ms: float,
    ) -> None:
        """Log feed push sync from client."""
        self.info(
            f"Feed push: {feed_count} feeds (created={created} updated={updated} unchanged={unchanged}) in {duration_ms:.0f}ms",
            component="sync",
            event="feed_push",
            context={
                "feed_count": feed_count,
                "created": created,
                "updated": updated,
                "unchanged": unchanged,
                "duration_ms": round(duration_ms),
            },
        )

    def sync_combined(
        self,
        duration_ms: float,
        new_digests: int,
        article_count: int,
        response_bytes: int,
        breakdown: dict,
    ) -> None:
        """Log combined sync endpoint completion."""
        self.info(
            f"Combined sync: {new_digests} digests, {article_count} articles, "
            f"{response_bytes} bytes in {duration_ms:.0f}ms",
            component="sync",
            event="combined_sync",
            context={
                "duration_ms": round(duration_ms),
                "new_digests": new_digests,
                "article_count": article_count,
                "response_bytes": response_bytes,
                **breakdown,
            },
        )

    # ===== Maintenance Events =====

    def maintenance_started(self) -> None:
        """Log daily maintenance start."""
        self.info(
            "Daily maintenance started",
            component="maintenance",
            event="started",
        )

    def maintenance_completed(
        self,
        digests_deleted: int = 0,
        articles_cleaned: int = 0,
        tombstones_cleaned: int = 0,
    ) -> None:
        """Log daily maintenance completion."""
        self.info(
            f"Daily maintenance completed: {digests_deleted} digests deleted, "
            f"{articles_cleaned} seen articles cleaned, {tombstones_cleaned} tombstones cleaned",
            component="maintenance",
            event="completed",
            context={
                "digests_deleted": digests_deleted,
                "articles_cleaned": articles_cleaned,
                "tombstones_cleaned": tombstones_cleaned,
            },
        )

    def client_inactivity_check(self, days_inactive: int, schedules_disabled: bool) -> None:
        """Log client inactivity check results."""
        if schedules_disabled:
            self.warning(
                f"Client inactive for {days_inactive} days, schedules auto-disabled",
                component="maintenance",
                event="inactivity_disable",
                context={"days_inactive": days_inactive},
            )
        else:
            self.debug(
                f"Client activity check passed (inactive {days_inactive} days)",
                component="maintenance",
                event="inactivity_check",
                context={"days_inactive": days_inactive},
            )


# Global singleton instance
digest_logger = DigestActivityLogger()


def configure_logging() -> None:
    """
    Configure all logging for the application.

    This should be called during application startup.
    Sets up both the standard Python logging and the digest activity logger.
    """
    settings = get_settings()

    # Configure standard Python logging
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Configure digest activity logger
    digest_logger.configure()
