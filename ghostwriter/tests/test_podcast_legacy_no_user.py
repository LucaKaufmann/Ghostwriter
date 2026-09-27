"""A valid legacy key without users keeps podcast setup access after auth 403."""

from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

import app.models  # noqa: F401 - register the complete fixture schema
from app.api import podcast
from app.core import security
from app.core.config import Settings, get_settings
from app.core.database import get_session
from app.models.digest import Digest
from app.models.podcast_episode import PodcastEpisode
from app.models.user import User


def test_valid_legacy_key_without_users_keeps_podcast_setup_but_invalid_key_fails(
    tmp_path, monkeypatch,
):
    settings = Settings(
        _env_file=None, data_dir=str(tmp_path),
        api_key="synthetic-legacy-key", jwt_secret="synthetic-jwt-secret",
    )
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    SQLModel.metadata.create_all(engine)
    digest_id = uuid4()
    with Session(engine) as session:
        session.add(Digest(
            id=digest_id, filename=f"{digest_id}.epub", period="manual", status="completed",
        ))
        session.add(PodcastEpisode(
            digest_ids=[str(digest_id)], trigger="manual", user_id=None, status="pending",
        ))
        session.commit()

    app = FastAPI()
    app.include_router(podcast.router, prefix="/api")

    def fixture_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = fixture_session
    app.dependency_overrides[get_settings] = lambda: settings
    monkeypatch.setattr(security, "engine", engine)
    monkeypatch.setattr(security, "get_settings", lambda: settings)
    monkeypatch.setattr(podcast, "get_settings", lambda: settings)

    @app.get("/account")
    async def account(user: Annotated[User, Depends(security.get_current_user)]):
        return {"id": str(user.id)}

    valid = {"X-API-Key": settings.api_key}
    invalid = {"X-API-Key": "wrong-key"}
    with TestClient(app) as client:
        assert client.get("/account", headers=valid).status_code == 403
        for path in (
            "/api/podcast/preferences", "/api/podcast/feed/info",
            f"/api/digests/{digest_id}/podcast",
        ):
            assert client.get(path, headers=valid).status_code == 200
            assert client.get(path, headers=invalid).status_code == 401
    engine.dispose()
