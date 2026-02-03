from datetime import timedelta

from sqlmodel import Session, select

from app.models.client_config import ClientConfig


def test_config_update_conflict(client):
    from app.core.database import engine

    with Session(engine) as session:
        config = session.exec(select(ClientConfig)).first()
        if config is None:
            config = ClientConfig()
            session.add(config)
            session.commit()
            session.refresh(config)
        server_ts = config.updated_at.isoformat()

    conflict_ts = (config.updated_at - timedelta(seconds=10)).isoformat()
    update = client.put(
        "/api/config",
        json={"min_word_count": 123, "client_updated_at": conflict_ts},
    )

    assert update.status_code == 409
    detail = update.json()["detail"]
    assert "server_updated_at" in detail
    assert "client_updated_at" in detail
