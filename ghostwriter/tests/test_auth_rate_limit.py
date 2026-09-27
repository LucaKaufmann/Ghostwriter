"""Request-level tests for the shared authentication rate limit."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from app.api.auth import router
from app.core import auth as auth_core
from app.core import rate_limit
from app.core.config import Settings, get_settings
from app.core.database import get_session


@pytest.fixture(autouse=True)
def clear_auth_limiter():
    rate_limit._auth_limiter._hits.clear()
    yield
    rate_limit._auth_limiter._hits.clear()


def _client(tmp_path, monkeypatch, *, enabled=True, maximum=2):
    settings = Settings(
        _env_file=None,
        data_dir=str(tmp_path),
        jwt_secret="synthetic-test-secret",
        auth_rate_limit_enabled=enabled,
        auth_rate_limit_max=maximum,
        auth_rate_limit_window_seconds=60,
    )
    engine = create_engine(
        f"sqlite:///{tmp_path / 'rate-limit.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    app = FastAPI()
    app.include_router(router)

    @app.middleware("http")
    async def synthetic_client_ip(request, call_next):
        # TestClient has one fixed client; simulate independent ASGI peers.
        request.scope["client"] = (request.headers.get("x-test-peer", "peer-a"), 1234)
        return await call_next(request)

    def session_dependency():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = session_dependency
    app.dependency_overrides[get_settings] = lambda: settings
    monkeypatch.setattr(rate_limit, "get_settings", lambda: settings)
    monkeypatch.setattr(auth_core, "get_settings", lambda: settings)
    return TestClient(app)


def test_login_and_register_share_bucket_and_recover_after_expiry(tmp_path, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(rate_limit.time, "time", lambda: clock[0])
    with _client(tmp_path, monkeypatch) as client:
        created = client.post(
            "/auth/register", json={"username": "admin", "password": "password-123"}
        )
        assert created.status_code == 200
        assert client.post(
            "/auth/login", json={"username": "admin", "password": "wrong"}
        ).status_code == 401
        assert client.post(
            "/auth/login", json={"username": "admin", "password": "password-123"}
        ).status_code == 429
        clock[0] += 61
        assert client.post(
            "/auth/login", json={"username": "admin", "password": "password-123"}
        ).status_code == 200


def test_register_threshold_and_independent_client_ips(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        body = {"username": "admin", "password": "password-123"}
        assert client.post("/auth/register", json=body).status_code == 200
        assert client.post("/auth/register", json=body).status_code == 403
        assert client.post("/auth/register", json=body).status_code == 429
        assert client.post(
            "/auth/login", json={"username": "admin", "password": "password-123"},
            headers={"x-test-peer": "peer-b"},
        ).status_code == 200


def test_disabled_rate_limit_does_not_reject(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch, enabled=False, maximum=1) as client:
        body = {"username": "missing", "password": "wrong"}
        assert [client.post("/auth/login", json=body).status_code for _ in range(3)] == [
            401, 401, 401
        ]
