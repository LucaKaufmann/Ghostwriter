"""KOReader plugin packaging and download endpoints."""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path
from typing import Annotated
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.core.auth import generate_api_token, get_token_prefix, hash_api_token
from app.core.database import get_session
from app.core.security import get_current_user
from app.models.api_token import APIToken
from app.models.user import User

router = APIRouter()

PLUGIN_TEMPLATE_DIR = (
    Path(__file__).resolve().parents[2] / "koreader" / "ghostwriter.koplugin"
)


class KoreaderPluginDownloadRequest(BaseModel):
    """Request payload for downloading a preconfigured KOReader plugin."""

    token_name: str = Field(
        default="KOReader Plugin",
        min_length=1,
        max_length=100,
        description="Name for the generated API token",
    )
    server_url: str | None = Field(
        default=None,
        max_length=2048,
        description=(
            "Optional Ghostwriter base URL to embed; defaults to current origin"
        ),
    )


def _escape_lua_string(value: str) -> str:
    """Escape a Python string for safe insertion into Lua double-quoted strings."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _normalize_server_url(request: Request, provided_url: str | None) -> str:
    """Normalize and validate the server URL embedded into the plugin."""
    candidate = (provided_url or "").strip()
    if not candidate:
        candidate = str(request.base_url)

    candidate = candidate.rstrip("/")
    if candidate.endswith("/api"):
        candidate = candidate[:-4]

    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid server_url. Expected absolute http(s) URL.",
        )

    # Preserve path (for reverse-proxy subpath deployments), drop query/fragment.
    normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    return normalized.rstrip("/")


def _inject_plugin_settings(
    settings_content: str,
    server_url: str,
    api_token: str,
) -> str:
    """
    Inject default server URL and API token into the KOReader plugin settings template.
    """
    escaped_url = _escape_lua_string(server_url)
    escaped_token = _escape_lua_string(api_token)

    updated, url_replacements = re.subn(
        r'(server_url\s*=\s*)""',
        rf'\1"{escaped_url}"',
        settings_content,
        count=1,
    )
    updated, token_replacements = re.subn(
        r'(api_token\s*=\s*)""',
        rf'\1"{escaped_token}"',
        updated,
        count=1,
    )
    if url_replacements != 1 or token_replacements != 1:
        raise ValueError(
            "Plugin settings template is missing required placeholder keys."
        )
    return updated


def _build_plugin_zip(server_url: str, api_token: str) -> bytes:
    """Build a zip bundle with preconfigured KOReader plugin defaults."""
    if not PLUGIN_TEMPLATE_DIR.exists() or not PLUGIN_TEMPLATE_DIR.is_dir():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="KOReader plugin template is not available on the server.",
        )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(PLUGIN_TEMPLATE_DIR.rglob("*")):
            if not file_path.is_file():
                continue

            rel_path = file_path.relative_to(PLUGIN_TEMPLATE_DIR)
            arcname = Path("ghostwriter.koplugin") / rel_path

            if rel_path.as_posix() == "settings.lua":
                raw_text = file_path.read_text(encoding="utf-8")
                try:
                    configured_text = _inject_plugin_settings(
                        raw_text,
                        server_url,
                        api_token,
                    )
                except ValueError as exc:
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="KOReader plugin settings template is invalid.",
                    ) from exc
                zf.writestr(arcname.as_posix(), configured_text.encode("utf-8"))
            else:
                zf.writestr(arcname.as_posix(), file_path.read_bytes())

    return buffer.getvalue()


@router.post("/koreader/download")
async def download_koreader_plugin(
    payload: KoreaderPluginDownloadRequest,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Session = Depends(get_session),
):
    """
    Generate and download a preconfigured KOReader plugin zip.

    This endpoint creates a new API token for the authenticated user,
    embeds the server URL + token into the plugin defaults, and returns
    a ready-to-install zip bundle.
    """
    server_url = _normalize_server_url(request, payload.server_url)

    raw_token = generate_api_token()
    token_hash = hash_api_token(raw_token)
    token_prefix = get_token_prefix(raw_token)

    api_token = APIToken(
        user_id=current_user.id,
        name=payload.token_name,
        token_hash=token_hash,
        token_prefix=token_prefix,
    )
    session.add(api_token)
    session.commit()

    zip_bytes = _build_plugin_zip(server_url=server_url, api_token=raw_token)

    filename = "ghostwriter.koplugin.zip"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(
        io.BytesIO(zip_bytes),
        media_type="application/zip",
        headers=headers,
    )
