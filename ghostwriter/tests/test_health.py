"""Tests for health and system endpoints."""

import base64
from datetime import datetime
import os
from pathlib import Path
from uuid import uuid4
import zipfile

from sqlmodel import Session

from app.core.database import engine
from app.models.digest import Digest

SECRET_MASK = "\u2022\u2022\u2022\u2022\u2022\u2022"


def test_root(client):
    """Test root endpoint returns service info."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "Ghostwriter"
    assert "version" in data


def test_health(client):
    """Test health endpoint."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"

    # Full status is exposed under /api/health
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert "version" in data
    assert "ai_provider" in data


def test_config(client):
    """Test config endpoint."""
    response = client.get("/api/health/config")
    assert response.status_code == 200
    data = response.json()
    assert "timezone" in data
    assert "ai_provider" in data
    assert "schedule_enabled" in data


def test_client_config_includes_cover_settings(client):
    """Client config endpoint should include digest cover settings."""
    response = client.get("/api/config")
    assert response.status_code == 200
    data = response.json()
    assert data["cover_enabled"] is False
    assert data["cover_provider"] == "gpt-image-1"
    assert data["cover_quality"] == "low"
    assert "cover_prompt" in data
    assert data["cover_openai_api_key"] == ""
    assert data["cover_gemini_api_key"] == ""


def test_client_config_cover_keys_are_masked_and_can_be_cleared(client):
    """Cover API keys should be masked on read and clearable via empty string."""
    update_response = client.put(
        "/api/config",
        json={
            "cover_openai_api_key": "sk-cover-test",
            "cover_gemini_api_key": "AIza-cover-test",
        },
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["cover_openai_api_key"] == SECRET_MASK
    assert updated["cover_gemini_api_key"] == SECRET_MASK

    get_response = client.get("/api/config")
    assert get_response.status_code == 200
    current = get_response.json()
    assert current["cover_openai_api_key"] == SECRET_MASK
    assert current["cover_gemini_api_key"] == SECRET_MASK

    clear_response = client.put(
        "/api/config",
        json={
            "cover_openai_api_key": "",
            "cover_gemini_api_key": "",
        },
    )
    assert clear_response.status_code == 200
    cleared = clear_response.json()
    assert cleared["cover_openai_api_key"] == ""
    assert cleared["cover_gemini_api_key"] == ""


def test_manual_cover_upload_activate_delete_flow(client):
    """Manual covers can be uploaded, activated, listed, and deleted."""
    tiny_png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4"
        "//8/AwAI/AL+X4xL9QAAAABJRU5ErkJggg=="
    )

    upload_one = client.post(
        "/api/config/covers/upload",
        files={"file": ("cover-one.png", tiny_png, "image/png")},
    )
    assert upload_one.status_code == 200
    cover_one = upload_one.json()
    assert cover_one["is_active"] is True
    assert cover_one["media_type"] == "image/jpeg"
    assert cover_one["preview_data_url"].startswith("data:image/jpeg;base64,")

    upload_two = client.post(
        "/api/config/covers/upload",
        files={"file": ("cover-two.png", tiny_png, "image/png")},
    )
    assert upload_two.status_code == 200
    cover_two = upload_two.json()
    assert cover_two["is_active"] is False

    list_response = client.get("/api/config/covers")
    assert list_response.status_code == 200
    covers = list_response.json()["covers"]
    assert len(covers) >= 2

    activate_response = client.post(f"/api/config/covers/{cover_two['id']}/activate")
    assert activate_response.status_code == 200
    activated = activate_response.json()
    assert activated["id"] == cover_two["id"]
    assert activated["is_active"] is True

    delete_active = client.delete(f"/api/config/covers/{cover_two['id']}")
    assert delete_active.status_code == 200
    remaining = delete_active.json()["covers"]
    assert all(item["id"] != cover_two["id"] for item in remaining)
    matching = [item for item in remaining if item["id"] == cover_one["id"]]
    assert matching and matching[0]["is_active"] is True


def test_digest_cover_endpoint_returns_embedded_cover(client):
    """Digest cover endpoint should return embedded EPUB cover image bytes."""
    epub_name = f"{uuid4()}.epub"
    output_dir = Path(os.environ["OUTPUT_DIR"])
    output_dir.mkdir(parents=True, exist_ok=True)
    epub_path = output_dir / epub_name

    cover_png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4"
        "//8/AwAI/AL+X4xL9QAAAABJRU5ErkJggg=="
    )

    with zipfile.ZipFile(epub_path, "w") as zf:
        zf.writestr(
            "cover.xhtml",
            '<html><body><img src="images/cover.png" alt="cover"/></body></html>',
        )
        zf.writestr("images/cover.png", cover_png)

    digest_id = uuid4()
    with Session(engine) as session:
        session.add(
            Digest(
                id=digest_id,
                filename=epub_name,
                period="manual",
                status="completed",
                stage="completed",
                created_at=datetime.utcnow(),
            )
        )
        session.commit()

    response = client.get(f"/api/digests/{digest_id}/cover")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content == cover_png
