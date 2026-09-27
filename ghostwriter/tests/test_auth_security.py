"""Authentication compatibility and deterministic DB session teardown."""

from __future__ import annotations

import asyncio
import gc
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI, Request
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

from app.api import podcast
from app.core import auth as auth_core
from app.core import security
from app.core.auth import create_access_token, generate_api_token, hash_api_token
from app.core.config import Settings, get_settings
from app.core.database import get_session
from app.core.security import verify_api_key
from app.models.api_token import APIToken
from app.models.user import User


@pytest.fixture
def auth_harness(tmp_path, monkeypatch):
    settings = Settings(
        _env_file=None,
        data_dir=str(tmp_path),
        api_key="",
        jwt_secret="synthetic-test-secret",
    )
    engine = create_engine(
        f"sqlite:///{tmp_path / 'security.db'}",
        connect_args={"check_same_thread": False},
        pool_size=1,
        max_overflow=0,
    )
    SQLModel.metadata.create_all(engine)
    app = FastAPI()

    def session_dependency():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = session_dependency
    app.dependency_overrides[get_settings] = lambda: settings
    monkeypatch.setattr(auth_core, "get_settings", lambda: settings)
    monkeypatch.setattr(security, "get_settings", lambda: settings)
    monkeypatch.setattr(security, "engine", engine)
    monkeypatch.setattr(podcast, "get_settings", lambda: settings)

    @app.get("/guarded", dependencies=[Depends(verify_api_key)])
    def guarded():
        return {"ok": True}

    @app.get("/account")
    async def account(user: Annotated[User, Depends(security.get_current_user)]):
        return {"username": user.username}

    @app.get("/podcast-guard")
    async def podcast_guard(
        request: Request, session: Annotated[Session, Depends(get_session)]
    ):
        await podcast._authorize_standard_or_feed_token(request, session, None)
        return {"ok": True}

    @app.get("/slow-stream", dependencies=[Depends(verify_api_key)])
    async def slow_stream():
        async def body():
            app.state.stream_started.set()
            await asyncio.to_thread(app.state.release_stream.wait, 5)
            yield b"done"

        return StreamingResponse(body())

    gc_was_enabled = gc.isenabled()
    gc.disable()
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client, engine, settings
    finally:
        if gc_was_enabled:
            gc.enable()
        engine.dispose()


def _add_user(engine):
    with Session(engine) as session:
        user = User(
            username="admin",
            password_hash="synthetic-hash",
            is_admin=True,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user.id


def test_setup_and_rejected_requests_release_pool(auth_harness):
    client, engine, _ = auth_harness
    assert engine.pool.checkedout() == 0
    assert client.get("/guarded").status_code == 200  # setup mode
    assert engine.pool.checkedout() == 0
    user_id = _add_user(engine)
    expired = create_access_token(
        user_id, "admin", expires_delta=timedelta(seconds=-1)
    )
    for headers in (
        {},
        {"Authorization": "Bearer invalid"},
        {"Authorization": f"Bearer {expired}"},
    ):
        assert client.get("/guarded", headers=headers).status_code == 401
        assert engine.pool.checkedout() == 0


def test_jwt_and_direct_podcast_auth_release_pool(auth_harness):
    client, engine, _ = auth_harness
    user_id = _add_user(engine)
    token = create_access_token(user_id, "admin")
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/guarded", headers=headers).status_code == 200
    assert engine.pool.checkedout() == 0
    assert client.get("/podcast-guard", headers=headers).status_code == 200
    assert engine.pool.checkedout() == 0


def test_api_token_last_use_revocation_and_legacy_key(auth_harness):
    client, engine, settings = auth_harness
    user_id = _add_user(engine)
    raw = generate_api_token()
    with Session(engine) as session:
        token = APIToken(
            user_id=user_id,
            name="synthetic mobile",
            token_hash=hash_api_token(raw),
            token_prefix=auth_core.get_token_prefix(raw),
        )
        session.add(token)
        session.commit()
        token_id = token.id

    assert client.get("/guarded", headers={"X-API-Key": raw}).status_code == 200
    assert engine.pool.checkedout() == 0
    with Session(engine) as session:
        persisted = session.get(APIToken, token_id)
        assert persisted.last_used_at is not None
        persisted.revoked_at = datetime.utcnow()
        session.add(persisted)
        session.commit()
    assert client.get("/guarded", headers={"X-API-Key": raw}).status_code == 401
    assert engine.pool.checkedout() == 0


def test_valid_legacy_key_without_account_is_forbidden_not_expired(auth_harness):
    client, engine, settings = auth_harness
    settings.api_key = "synthetic-legacy-key"
    valid = client.get("/account", headers={"X-API-Key": settings.api_key})
    assert valid.status_code == 403, valid.text
    assert "WWW-Authenticate" not in valid.headers
    assert client.get("/account", headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.get("/account").status_code == 401
    assert engine.pool.checkedout() == 0

    settings.api_key = "synthetic-legacy-key"
    assert client.get(
        "/guarded", headers={"X-API-Key": "synthetic-legacy-key"}
    ).status_code == 200
    assert engine.pool.checkedout() == 0


def test_query_exception_releases_pool(auth_harness):
    client, engine, _ = auth_harness

    def fail_user_query(conn, cursor, statement, parameters, context, executemany):
        if "SELECT" in statement and "user" in statement.lower():
            raise RuntimeError("synthetic query failure")

    event.listen(engine, "before_cursor_execute", fail_user_query)
    try:
        assert client.get("/guarded").status_code == 500
        assert engine.pool.checkedout() == 0
    finally:
        event.remove(engine, "before_cursor_execute", fail_user_query)


def test_auth_connection_is_released_before_stream_finishes(auth_harness):
    client, engine, _ = auth_harness
    client.app.state.stream_started = threading.Event()
    client.app.state.release_stream = threading.Event()
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(client.get, "/slow-stream")
        try:
            assert client.app.state.stream_started.wait(timeout=5)
            assert not future.done()
            assert engine.pool.checkedout() == 0
        finally:
            client.app.state.release_stream.set()
        assert future.result(timeout=5).status_code == 200
