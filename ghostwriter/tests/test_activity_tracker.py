from datetime import datetime, timedelta
import importlib

from sqlmodel import Session, select

from app.models.client_settings import ClientSettings
from app.models.schedule import Schedule


def _seed_schedules(session: Session, enabled: bool) -> None:
    for period in ["morning", "noon", "evening"]:
        session.add(
            Schedule(
                period=period,
                hour=7,
                minute=0,
                enabled=enabled,
                timezone="UTC",
            )
        )
    session.commit()


def test_check_inactivity_disables_schedules():
    from app.core.database import engine
    import app.services.activity_tracker as activity_tracker
    activity_tracker = importlib.reload(activity_tracker)

    with Session(engine) as session:
        _seed_schedules(session, enabled=True)
        settings = ClientSettings(
            auto_disable_enabled=True,
            auto_disable_after_days=1,
            last_heartbeat_at=datetime.utcnow() - timedelta(days=2),
        )
        session.add(settings)
        session.commit()

    disabled = activity_tracker.check_inactivity()
    assert disabled is True

    with Session(engine) as session:
        schedules = session.exec(select(Schedule)).all()
        assert all(not s.enabled for s in schedules)
        settings = session.exec(select(ClientSettings)).first()
        assert settings is not None
        assert settings.schedules_auto_disabled is True


def test_record_heartbeat_reenables_schedules():
    from app.core.database import engine
    import app.services.activity_tracker as activity_tracker
    activity_tracker = importlib.reload(activity_tracker)

    with Session(engine) as session:
        _seed_schedules(session, enabled=False)
        settings = ClientSettings(
            schedules_auto_disabled=True,
            auto_disabled_at=datetime.utcnow() - timedelta(days=1),
        )
        session.add(settings)
        session.commit()

    activity_tracker.record_heartbeat()

    with Session(engine) as session:
        schedules = session.exec(select(Schedule)).all()
        assert all(s.enabled for s in schedules)
        settings = session.exec(select(ClientSettings)).first()
        assert settings is not None
        assert settings.schedules_auto_disabled is False
