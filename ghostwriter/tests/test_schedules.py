from sqlmodel import Session

from app.models.schedule import Schedule


def _seed_schedule(session: Session, period: str = "morning") -> Schedule:
    schedule = Schedule(period=period, hour=7, minute=0, enabled=True, timezone="UTC")
    session.add(schedule)
    session.commit()
    session.refresh(schedule)
    return schedule


def test_get_update_enable_disable_schedule(client):
    from app.core.database import engine

    with Session(engine) as session:
        schedule = _seed_schedule(session, period="morning")

    get_resp = client.get("/api/schedules/morning")
    assert get_resp.status_code == 200
    assert get_resp.json()["period"] == "morning"

    update = client.put("/api/schedules/morning", json={"hour": 9, "minute": 30})
    assert update.status_code == 200
    assert update.json()["hour"] == 9
    assert update.json()["minute"] == 30

    disable = client.post("/api/schedules/morning/disable")
    assert disable.status_code == 200
    assert disable.json()["enabled"] is False

    enable = client.post("/api/schedules/morning/enable")
    assert enable.status_code == 200
    assert enable.json()["enabled"] is True
