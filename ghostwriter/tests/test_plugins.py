"""Tests for KOReader plugin download endpoints."""

from __future__ import annotations

import io
import re
import zipfile
from datetime import datetime
from uuid import uuid4

from sqlmodel import Session, select

from app.core.auth import (
    create_access_token,
    get_token_prefix,
    hash_password,
    verify_api_token,
)
from app.core.database import engine
from app.models.api_token import APIToken
from app.models.user import User


def _create_user_and_jwt() -> tuple[User, str]:
    username = f"plugins-{uuid4().hex[:8]}"
    with Session(engine) as session:
        user = User(
            username=username,
            password_hash=hash_password("test-password-123"),
            is_admin=True,
            last_login_at=datetime.utcnow(),
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        jwt_token = create_access_token(user.id, user.username)
        return user, jwt_token


def test_download_koreader_plugin_requires_auth(client):
    """Download endpoint should reject unauthenticated requests."""
    response = client.post(
        "/api/plugins/koreader/download",
        json={"token_name": "KOReader"},
    )
    assert response.status_code == 401


def test_download_koreader_plugin_embeds_settings_and_creates_token(client):
    """Endpoint should return configured zip and persist a matching API token."""
    user, jwt_token = _create_user_and_jwt()
    response = client.post(
        "/api/plugins/koreader/download",
        json={
            "token_name": "KOReader Device",
            "server_url": "https://reader.example.com/api/",
        },
        headers={"Authorization": f"Bearer {jwt_token}"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/zip")
    assert "ghostwriter.koplugin.zip" in response.headers.get(
        "content-disposition",
        "",
    )

    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = set(archive.namelist())
        assert "ghostwriter.koplugin/ghostwriter_settings.lua" in names
        settings_lua = archive.read(
            "ghostwriter.koplugin/ghostwriter_settings.lua"
        ).decode(
            "utf-8"
        )

    assert 'server_url = "https://reader.example.com"' in settings_lua

    token_match = re.search(r'api_token\s*=\s*"(gw_[^"]+)"', settings_lua)
    assert token_match is not None
    embedded_token = token_match.group(1)

    with Session(engine) as session:
        tokens = session.exec(
            select(APIToken)
            .where(APIToken.user_id == user.id)
            .where(APIToken.name == "KOReader Device")
            .where(APIToken.revoked_at.is_(None))
        ).all()

    assert len(tokens) == 1
    token_record = tokens[0]
    assert token_record.token_prefix == get_token_prefix(embedded_token)
    assert verify_api_token(embedded_token, token_record.token_hash)


def test_download_koreader_plugin_uses_request_origin_when_server_url_missing(
    client,
):
    """When server_url is omitted, plugin should default to the request origin."""
    user, jwt_token = _create_user_and_jwt()
    response = client.post(
        "/api/plugins/koreader/download",
        json={"token_name": "KOReader Auto URL"},
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert response.status_code == 200

    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        settings_lua = archive.read(
            "ghostwriter.koplugin/ghostwriter_settings.lua"
        ).decode(
            "utf-8"
        )

    assert 'server_url = "http://testserver"' in settings_lua


def test_download_koreader_plugin_uses_koreader_lfs_module(client):
    """Packaged plugin should use KOReader's bundled lfs shim."""
    _, jwt_token = _create_user_and_jwt()
    response = client.post(
        "/api/plugins/koreader/download",
        json={"token_name": "KOReader LFS Check"},
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert response.status_code == 200

    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        sync_lua = archive.read(
            "ghostwriter.koplugin/ghostwriter_sync.lua"
        ).decode(
            "utf-8"
        )

    assert 'require("libs/libkoreader-lfs")' in sync_lua
    assert 'require("lfs")' not in sync_lua
