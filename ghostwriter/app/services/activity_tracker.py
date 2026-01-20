"""Client activity tracking service.

Handles heartbeat recording, download tracking, and inactivity detection
for auto-disabling schedules when the client app is uninstalled or inactive.
"""

import logging
from datetime import datetime, timedelta

from sqlmodel import Session, select

from app.core.database import engine
from app.models.client_settings import ClientSettings
from app.models.schedule import Schedule

logger = logging.getLogger(__name__)


def get_client_settings() -> ClientSettings:
    """
    Get the singleton ClientSettings, creating it if it doesn't exist.

    Returns:
        The ClientSettings instance.
    """
    with Session(engine) as session:
        settings = session.exec(select(ClientSettings)).first()

        if not settings:
            settings = ClientSettings()
            session.add(settings)
            session.commit()
            session.refresh(settings)
            logger.info("Created initial client settings")

        return settings


def record_heartbeat() -> ClientSettings:
    """
    Record a heartbeat from the client.

    This indicates the client app is still active. Also re-enables
    schedules if they were auto-disabled.

    Returns:
        Updated ClientSettings.
    """
    with Session(engine) as session:
        settings = session.exec(select(ClientSettings)).first()

        if not settings:
            settings = ClientSettings()

        now = datetime.utcnow()
        settings.last_heartbeat_at = now
        settings.updated_at = now

        # Re-enable schedules if they were auto-disabled
        if settings.schedules_auto_disabled:
            _reenable_schedules(session)
            settings.schedules_auto_disabled = False
            settings.auto_disabled_at = None
            logger.info("Schedules re-enabled due to client heartbeat")

        session.add(settings)
        session.commit()
        session.refresh(settings)

        logger.debug(f"Recorded heartbeat at {now}")
        return settings


def record_download() -> ClientSettings:
    """
    Record a digest download.

    This indicates the client is actively using the service.
    Also re-enables schedules if they were auto-disabled.

    Returns:
        Updated ClientSettings.
    """
    with Session(engine) as session:
        settings = session.exec(select(ClientSettings)).first()

        if not settings:
            settings = ClientSettings()

        now = datetime.utcnow()
        settings.last_download_at = now
        settings.updated_at = now

        # Re-enable schedules if they were auto-disabled
        if settings.schedules_auto_disabled:
            _reenable_schedules(session)
            settings.schedules_auto_disabled = False
            settings.auto_disabled_at = None
            logger.info("Schedules re-enabled due to digest download")

        session.add(settings)
        session.commit()
        session.refresh(settings)

        logger.debug(f"Recorded download at {now}")
        return settings


def record_feed_sync() -> ClientSettings:
    """
    Record a feed sync from the client.

    Returns:
        Updated ClientSettings.
    """
    with Session(engine) as session:
        settings = session.exec(select(ClientSettings)).first()

        if not settings:
            settings = ClientSettings()

        now = datetime.utcnow()
        settings.last_feed_sync_at = now
        settings.updated_at = now

        # Re-enable schedules if they were auto-disabled
        if settings.schedules_auto_disabled:
            _reenable_schedules(session)
            settings.schedules_auto_disabled = False
            settings.auto_disabled_at = None
            logger.info("Schedules re-enabled due to feed sync")

        session.add(settings)
        session.commit()
        session.refresh(settings)

        logger.debug(f"Recorded feed sync at {now}")
        return settings


def update_settings(
    auto_disable_enabled: bool | None = None,
    auto_disable_after_days: int | None = None,
) -> ClientSettings:
    """
    Update client settings.

    Args:
        auto_disable_enabled: Whether to auto-disable on inactivity.
        auto_disable_after_days: Days before auto-disable triggers.

    Returns:
        Updated ClientSettings.
    """
    with Session(engine) as session:
        settings = session.exec(select(ClientSettings)).first()

        if not settings:
            settings = ClientSettings()

        if auto_disable_enabled is not None:
            settings.auto_disable_enabled = auto_disable_enabled
        if auto_disable_after_days is not None:
            settings.auto_disable_after_days = auto_disable_after_days

        settings.updated_at = datetime.utcnow()

        session.add(settings)
        session.commit()
        session.refresh(settings)

        logger.info(
            f"Updated settings: auto_disable_enabled={settings.auto_disable_enabled}, "
            f"auto_disable_after_days={settings.auto_disable_after_days}"
        )
        return settings


def check_inactivity() -> bool:
    """
    Check for client inactivity and auto-disable schedules if needed.

    This should be called periodically (e.g., daily) by a scheduled job.

    Returns:
        True if schedules were disabled due to inactivity.
    """
    with Session(engine) as session:
        settings = session.exec(select(ClientSettings)).first()

        if not settings:
            # No settings = no activity ever recorded
            settings = ClientSettings()
            session.add(settings)
            session.commit()

        # Skip if auto-disable is turned off
        if not settings.auto_disable_enabled:
            logger.debug("Auto-disable is disabled, skipping inactivity check")
            return False

        # Skip if already auto-disabled
        if settings.schedules_auto_disabled:
            logger.debug("Schedules already auto-disabled")
            return False

        # Calculate last activity time
        last_activity = _get_last_activity_time(settings)

        if last_activity is None:
            # No activity ever recorded - check if schedules exist and have run
            # Give a grace period from settings creation
            grace_period = settings.created_at + timedelta(days=settings.auto_disable_after_days)
            if datetime.utcnow() > grace_period:
                logger.warning("No client activity recorded since creation, disabling schedules")
                _disable_all_schedules(session)
                settings.schedules_auto_disabled = True
                settings.auto_disabled_at = datetime.utcnow()
                settings.updated_at = datetime.utcnow()
                session.add(settings)
                session.commit()
                return True
            return False

        # Check if inactive for too long
        inactive_threshold = datetime.utcnow() - timedelta(days=settings.auto_disable_after_days)

        if last_activity < inactive_threshold:
            days_inactive = (datetime.utcnow() - last_activity).days
            logger.warning(
                f"Client inactive for {days_inactive} days (threshold: {settings.auto_disable_after_days}), "
                "disabling schedules"
            )
            _disable_all_schedules(session)
            settings.schedules_auto_disabled = True
            settings.auto_disabled_at = datetime.utcnow()
            settings.updated_at = datetime.utcnow()
            session.add(settings)
            session.commit()
            return True

        logger.debug(f"Client active, last activity: {last_activity}")
        return False


def get_days_until_auto_disable() -> int | None:
    """
    Calculate days remaining until auto-disable triggers.

    Returns:
        Days until auto-disable, or None if auto-disable is off or already triggered.
    """
    settings = get_client_settings()

    if not settings.auto_disable_enabled:
        return None

    if settings.schedules_auto_disabled:
        return None

    last_activity = _get_last_activity_time(settings)

    if last_activity is None:
        # Use creation time as baseline
        last_activity = settings.created_at

    days_since_activity = (datetime.utcnow() - last_activity).days
    days_remaining = settings.auto_disable_after_days - days_since_activity

    return max(0, days_remaining)


def _get_last_activity_time(settings: ClientSettings) -> datetime | None:
    """Get the most recent activity timestamp."""
    timestamps = [
        settings.last_heartbeat_at,
        settings.last_download_at,
        settings.last_feed_sync_at,
    ]
    valid_timestamps = [t for t in timestamps if t is not None]

    if not valid_timestamps:
        return None

    return max(valid_timestamps)


def _disable_all_schedules(session: Session) -> None:
    """Disable all schedules."""
    from app.worker.scheduler import update_schedule

    schedules = session.exec(select(Schedule)).all()
    for schedule in schedules:
        if schedule.enabled:
            update_schedule(period=schedule.period, enabled=False)
            logger.info(f"Auto-disabled {schedule.period} schedule")


def _reenable_schedules(session: Session) -> None:
    """Re-enable all schedules that were auto-disabled."""
    from app.worker.scheduler import update_schedule

    schedules = session.exec(select(Schedule)).all()
    for schedule in schedules:
        if not schedule.enabled:
            update_schedule(period=schedule.period, enabled=True)
            logger.info(f"Re-enabled {schedule.period} schedule")
