"""APScheduler configuration for scheduled digest generation."""

import logging
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlmodel import Session, select

from app.core.config import get_settings
from app.core.database import engine
from app.models.schedule import Schedule
from app.worker.bindery import generate_digest

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()

# Default schedule times (used when creating initial schedules)
DEFAULT_SCHEDULES = {
    "morning": {"hour": 7, "minute": 0},
    "noon": {"hour": 12, "minute": 0},
    "evening": {"hour": 18, "minute": 0},
}


def setup_scheduler() -> None:
    """
    Configure and start the APScheduler.

    Loads schedule configuration from database (falling back to env vars
    for initial setup) and sets up cron jobs for each enabled period.
    Also sets up the daily maintenance job for cleanup and inactivity checking.
    """
    settings = get_settings()

    if not settings.schedule_enabled:
        logger.info("Scheduled runs disabled via config")
        return

    # Ensure default schedules exist in database
    _ensure_default_schedules()

    # Load and configure schedules from database
    _load_schedules_from_db()

    # Add daily maintenance job (runs at 3 AM UTC)
    scheduler.add_job(
        _daily_maintenance,
        CronTrigger(hour=3, minute=0),
        id="daily_maintenance",
        replace_existing=True,
        misfire_grace_time=3600,  # 1 hour grace
    )
    logger.info("Scheduled daily maintenance job at 03:00 UTC")

    scheduler.start()
    logger.info("Scheduler started")


async def _daily_maintenance() -> None:
    """
    Run daily maintenance tasks.

    This includes:
    - Checking for client inactivity
    - Cleaning up old digests
    - Cleaning up old seen article records
    """
    from app.worker.cleanup import (
        check_client_inactivity,
        cleanup_old_digests,
        cleanup_seen_articles,
    )

    logger.info("Running daily maintenance")

    try:
        # Check for client inactivity first
        await check_client_inactivity()

        # Run cleanup tasks
        await cleanup_old_digests()
        await cleanup_seen_articles()

        logger.info("Daily maintenance completed")
    except Exception as e:
        logger.exception(f"Daily maintenance failed: {e}")


def _ensure_default_schedules() -> None:
    """
    Ensure default schedule records exist in the database.

    Creates schedules based on environment config if they don't exist.
    """
    settings = get_settings()

    with Session(engine) as session:
        for period, defaults in DEFAULT_SCHEDULES.items():
            existing = session.exec(
                select(Schedule).where(Schedule.period == period)
            ).first()

            if not existing:
                # Parse time from settings if available
                time_str = getattr(settings, f"schedule_{period}", None)
                if time_str:
                    try:
                        hour, minute = map(int, time_str.split(":"))
                    except ValueError:
                        hour, minute = defaults["hour"], defaults["minute"]
                else:
                    hour, minute = defaults["hour"], defaults["minute"]

                schedule = Schedule(
                    period=period,
                    hour=hour,
                    minute=minute,
                    enabled=True,
                    timezone=settings.timezone,
                )
                session.add(schedule)
                logger.info(f"Created default schedule for {period} at {hour:02d}:{minute:02d}")

        session.commit()


def _load_schedules_from_db() -> None:
    """Load all enabled schedules from database and configure APScheduler jobs."""
    with Session(engine) as session:
        schedules = session.exec(select(Schedule)).all()

        for schedule in schedules:
            if schedule.enabled:
                _add_schedule_job(schedule)
            else:
                _remove_schedule_job(schedule.period)


def _add_schedule_job(schedule: Schedule) -> None:
    """
    Add or update a scheduled job for a period.

    Args:
        schedule: The Schedule entity with timing configuration.
    """
    job_id = f"digest_{schedule.period}"

    try:
        # Get timezone
        tz = pytz.timezone(schedule.timezone)
    except pytz.exceptions.UnknownTimeZoneError:
        logger.warning(f"Unknown timezone '{schedule.timezone}', using UTC")
        tz = pytz.UTC

    trigger = CronTrigger(
        hour=schedule.hour,
        minute=schedule.minute,
        timezone=tz,
    )

    scheduler.add_job(
        _scheduled_digest,
        trigger,
        args=[schedule.period],
        id=job_id,
        replace_existing=True,
        misfire_grace_time=300,  # 5 minute grace
    )
    logger.info(
        f"Scheduled {schedule.period} digest at {schedule.hour:02d}:{schedule.minute:02d} ({schedule.timezone})"
    )


def _remove_schedule_job(period: str) -> None:
    """
    Remove a scheduled job.

    Args:
        period: The period name (morning, noon, evening).
    """
    job_id = f"digest_{period}"
    try:
        scheduler.remove_job(job_id)
        logger.info(f"Removed schedule job for {period}")
    except Exception:
        pass  # Job might not exist


async def _scheduled_digest(period: str) -> None:
    """
    Execute a scheduled digest generation.

    Updates the schedule's last_run_at timestamp on success.

    Args:
        period: The period name.
    """
    logger.info(f"Running scheduled {period} digest")
    try:
        digest_id = await generate_digest(period)
        if digest_id:
            logger.info(f"Scheduled {period} digest started: {digest_id}")
            # Update last run time
            _update_last_run(period, digest_id)
        else:
            logger.warning(f"Could not start scheduled {period} digest (job running?)")
    except Exception as e:
        logger.exception(f"Scheduled {period} digest failed: {e}")


def _update_last_run(period: str, digest_id: UUID) -> None:
    """
    Update the last run timestamp for a schedule.

    Args:
        period: The period name.
        digest_id: The ID of the generated digest.
    """
    with Session(engine) as session:
        schedule = session.exec(
            select(Schedule).where(Schedule.period == period)
        ).first()
        if schedule:
            schedule.last_run_at = datetime.utcnow()
            schedule.last_run_digest_id = digest_id
            schedule.updated_at = datetime.utcnow()
            session.add(schedule)
            session.commit()


def update_schedule(
    period: str,
    hour: int | None = None,
    minute: int | None = None,
    enabled: bool | None = None,
    timezone: str | None = None,
) -> Schedule | None:
    """
    Update a schedule configuration.

    Modifies the database record and reconfigures the APScheduler job.

    Args:
        period: The period to update (morning, noon, evening).
        hour: New hour (0-23), or None to keep current.
        minute: New minute (0-59), or None to keep current.
        enabled: New enabled state, or None to keep current.
        timezone: New timezone, or None to keep current.

    Returns:
        The updated Schedule, or None if not found.
    """
    with Session(engine) as session:
        schedule = session.exec(
            select(Schedule).where(Schedule.period == period)
        ).first()

        if not schedule:
            return None

        if hour is not None:
            schedule.hour = hour
        if minute is not None:
            schedule.minute = minute
        if enabled is not None:
            schedule.enabled = enabled
        if timezone is not None:
            schedule.timezone = timezone

        schedule.updated_at = datetime.utcnow()
        session.add(schedule)
        session.commit()
        session.refresh(schedule)

        # Update the APScheduler job
        if schedule.enabled:
            _add_schedule_job(schedule)
        else:
            _remove_schedule_job(period)

        logger.info(f"Updated schedule for {period}: {schedule.hour:02d}:{schedule.minute:02d} enabled={schedule.enabled}")
        return schedule


def get_schedule(period: str) -> Schedule | None:
    """
    Get a schedule by period.

    Args:
        period: The period name.

    Returns:
        The Schedule, or None if not found.
    """
    with Session(engine) as session:
        return session.exec(
            select(Schedule).where(Schedule.period == period)
        ).first()


def get_all_schedules() -> list[Schedule]:
    """
    Get all schedules.

    Returns:
        List of all Schedule records.
    """
    with Session(engine) as session:
        return list(session.exec(select(Schedule)).all())


def get_next_run_time(schedule: Schedule) -> datetime | None:
    """
    Calculate the next run time for a schedule.

    Args:
        schedule: The schedule to check.

    Returns:
        The next run datetime in UTC, or None if not scheduled.
    """
    if not schedule.enabled:
        return None

    job_id = f"digest_{schedule.period}"
    job = scheduler.get_job(job_id)

    if job and job.next_run_time:
        return job.next_run_time.astimezone(pytz.UTC).replace(tzinfo=None)

    return None


def trigger_schedule_now(period: str) -> UUID | None:
    """
    Manually trigger a scheduled period immediately.

    This is useful for testing schedules without waiting.

    Args:
        period: The period to trigger (morning, noon, evening).

    Returns:
        The digest ID if started, None if a job is already running.
    """
    import asyncio

    async def _run():
        return await generate_digest(period)

    # Run the async function
    loop = asyncio.get_event_loop()
    if loop.is_running():
        # We're already in an async context
        future = asyncio.ensure_future(_run())
        return None  # Can't block here, return immediately
    else:
        return loop.run_until_complete(_run())


def shutdown_scheduler() -> None:
    """Shutdown the scheduler gracefully."""
    if scheduler.running:
        scheduler.shutdown(wait=True)
        logger.info("Scheduler shutdown complete")
