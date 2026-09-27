"""Synthetic OAuth and API requests exercise configuration isolation."""

import asyncio
from urllib.parse import parse_qs

import httpx
import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import Settings
from app.models.wallabag_config import WallabagConfig
from app.services.wallabag_service import WallabagService


def settings(**changes):
    values = {
        "wallabag_url": "https://saved.example.test",
        "wallabag_client_id": "client-a",
        "wallabag_client_secret": "secret-a",
        "wallabag_username": "account-a",
        "wallabag_password": "password-a",
    }
    values.update(changes)
    return Settings(**values)


@pytest.fixture
def oauth(monkeypatch):
    calls = []
    tokens = {}
    state = {"fail": False, "now": 1000.0}
    real_client = httpx.AsyncClient

    def identity(url, form):
        return (
            str(url).split("/oauth/")[0],
            *(
                form[k][0]
                for k in ("client_id", "client_secret", "username", "password")
            ),
        )

    async def respond(request):
        calls.append(request)
        if request.url.path == "/oauth/v2/token":
            if state["fail"]:
                return httpx.Response(503, text="Synthetic outage")
            key = identity(request.url, parse_qs(request.content.decode()))
            token = f"token-{len(calls)}"
            tokens[token] = key
            await asyncio.sleep(0)  # Interleave concurrent configurations.
            return httpx.Response(200, json={"access_token": token, "expires_in": 120})
        token = request.headers["Authorization"].removeprefix("Bearer ")
        assert tokens[token][0] == str(request.url).split("/api/")[0]
        return httpx.Response(200, json={"_embedded": {"items": []}})

    monkeypatch.setattr(
        "app.services.wallabag_service.httpx.AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(respond), **kwargs),
    )
    monkeypatch.setattr("app.services.wallabag_service.time.time", lambda: state["now"])
    return calls, tokens, state


@pytest.mark.asyncio
async def test_reuse_expiry_failed_refresh_and_recovery(oauth):
    calls, _, state = oauth
    service = WallabagService(settings())
    await service.fetch_unread_articles()
    await service.mark_processed(1)
    assert sum(r.url.path == "/oauth/v2/token" for r in calls) == 1
    old_token = calls[-1].headers["Authorization"]
    state.update(now=1061.0, fail=True)
    with pytest.raises(httpx.HTTPStatusError):
        await service.fetch_unread_articles()
    assert calls[-1].url.path == "/oauth/v2/token"  # No API call with expired token.
    state["fail"] = False
    await service.fetch_unread_articles()
    assert calls[-1].headers["Authorization"] != old_token


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,new",
    [
        ("wallabag_url", "https://other.example.test"),
        ("wallabag_client_id", "client-b"),
        ("wallabag_client_secret", "secret-b"),
        ("wallabag_username", "account-b"),
        ("wallabag_password", "password-b"),
    ],
)
async def test_changed_configuration_never_reuses_previous_token(oauth, field, new):
    calls, tokens, _ = oauth
    original = WallabagService(settings())
    await original.fetch_unread_articles()
    previous = calls[-1].headers["Authorization"]
    changed = WallabagService(settings(**{field: new}))
    await changed.fetch_unread_articles()
    current = calls[-1].headers["Authorization"]
    assert previous != current
    assert len(tokens) == 2
    await original.fetch_unread_articles()
    assert calls[-1].headers["Authorization"] == previous


@pytest.mark.asyncio
async def test_source_settings_mutation_cannot_redirect_inflight_service(oauth):
    calls, _, _ = oauth
    source = settings()
    service = WallabagService(source)
    await service.fetch_unread_articles()
    source.wallabag_url = "https://other.example.test"
    source.wallabag_password = "changed"
    await service.mark_processed(123)
    assert calls[-1].url.host == "saved.example.test"
    new_service = WallabagService(source)
    await new_service.fetch_unread_articles()
    assert calls[-1].url.host == "other.example.test"


@pytest.mark.asyncio
async def test_concurrent_configurations_remain_isolated(oauth):
    calls, tokens, _ = oauth
    services = [
        WallabagService(settings(wallabag_url=f"https://{name}.example.test"))
        for name in ("one", "two")
    ]
    await asyncio.gather(*(s.fetch_unread_articles() for s in services))
    assert len(tokens) == 2
    await asyncio.gather(*(s.mark_processed(1) for s in services))
    assert sum(r.url.path == "/oauth/v2/token" for r in calls) == 2


@pytest.mark.asyncio
async def test_db_update_gets_new_credentials_and_empty_db_falls_back(oauth, tmp_path):
    calls, tokens, _ = oauth
    engine = create_engine(f"sqlite:///{tmp_path / 'wallabag.db'}")
    SQLModel.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            fallback = WallabagService.from_db_or_settings(session, settings())
            await fallback.fetch_unread_articles()
            config = WallabagConfig(
                url="https://db.example.test",
                client_id="db-client",
                client_secret="db-secret",
                username="db-account",
                password="db-password",
                mode="summarize",
            )
            session.add(config)
            session.commit()
            original = WallabagService.from_db_or_settings(session, settings())
            await original.fetch_unread_articles()
            assert original.settings.wallabag_mode == "summarize"
            config.password = "updated-password"
            session.add(config)
            session.commit()
            updated = WallabagService.from_db_or_settings(session, settings())
            await updated.fetch_unread_articles()
            token = calls[-1].headers["Authorization"].removeprefix("Bearer ")
            assert tokens[token][-1] == "updated-password"
            assert original.settings.wallabag_password == "db-password"
            assert len(tokens) == 3
    finally:
        engine.dispose()
