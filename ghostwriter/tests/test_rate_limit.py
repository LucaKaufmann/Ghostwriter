import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.core import rate_limit
from app.core.config import Settings


def _request_for_ip(ip: str) -> Request:
    scope = {"type": "http", "client": (ip, 1234), "headers": []}
    return Request(scope)


def test_check_auth_rate_limit_blocks_after_threshold(monkeypatch):
    def _fake_settings():
        return Settings(
            auth_rate_limit_enabled=True,
            auth_rate_limit_max=2,
            auth_rate_limit_window_seconds=60,
        )

    monkeypatch.setattr(rate_limit, "get_settings", _fake_settings)
    rate_limit._auth_limiter._hits.clear()

    request = _request_for_ip("1.2.3.4")
    rate_limit.check_auth_rate_limit(request)
    rate_limit.check_auth_rate_limit(request)

    with pytest.raises(HTTPException) as exc:
        rate_limit.check_auth_rate_limit(request)

    assert exc.value.status_code == 429
