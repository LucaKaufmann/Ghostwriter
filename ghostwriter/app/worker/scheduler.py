"""APScheduler configuration for scheduled digest generation."""

import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import get_settings
from app.worker.bindery import generate_digest

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


def setup_scheduler() -> None:
    """
    Configure and start the APScheduler.

    Reads schedule configuration from environment and sets up
    cron jobs for morning, noon, and evening digest generation.
    """
    settings = get_settings()

    if not settings.schedule_enabled:
        logger.info("Scheduled runs disabled")
        return

    # Parse schedule times and add jobs
    if settings.schedule_morning:
        _add_schedule_job("morning", settings.schedule_morning)

    if settings.schedule_noon:
        _add_schedule_job("noon", settings.schedule_noon)

    if settings.schedule_evening:
        _add_schedule_job("evening", settings.schedule_evening)

    scheduler.start()
    logger.info("Scheduler started")


def _add_schedule_job(period: str, time_str: str) -> None:
    """
    Add a scheduled job for a time period.

    Args:
        period: The period name (morning, noon, evening).
        time_str: Time in 24h format (HH:MM).
    """
    try:
        hour, minute = time_str.split(":")
        trigger = CronTrigger(hour=int(hour), minute=int(minute))

        scheduler.add_job(
            _scheduled_digest,
            trigger,
            args=[period],
            id=f"digest_{period}",
            replace_existing=True,
            misfire_grace_time=300,  # 5 minute grace
        )
        logger.info(f"Scheduled {period} digest at {time_str}")

    except ValueError as e:
        logger.error(f"Invalid schedule time '{time_str}' for {period}: {e}")


async def _scheduled_digest(period: str) -> None:
    """
    Execute a scheduled digest generation.

    Args:
        period: The period name.
    """
    logger.info(f"Running scheduled {period} digest")
    try:
        digest_id = await generate_digest(period)
        if digest_id:
            logger.info(f"Scheduled {period} digest started: {digest_id}")
        else:
            logger.warning(f"Could not start scheduled {period} digest (job running?)")
    except Exception as e:
        logger.exception(f"Scheduled {period} digest failed: {e}")


def shutdown_scheduler() -> None:
    """Shutdown the scheduler gracefully."""
    if scheduler.running:
        scheduler.shutdown(wait=True)
        logger.info("Scheduler shutdown complete")
