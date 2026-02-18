"""Tests for PDF-related config settings."""

from sqlmodel import Session
from sqlmodel import delete as sql_delete

from app.core.database import engine
from app.models.client_config import ClientConfig


def _reset_client_config() -> None:
    with Session(engine) as session:
        session.exec(sql_delete(ClientConfig))
        session.commit()


def test_config_defaults_include_pdf_settings(client) -> None:
    _reset_client_config()
    response = client.get("/api/config")
    assert response.status_code == 200
    payload = response.json()
    assert payload["pdf_enabled"] is False
    assert payload["pdf_page_size"] == "A4"


def test_config_update_pdf_settings(client) -> None:
    _reset_client_config()
    response = client.put(
        "/api/config",
        json={
            "pdf_enabled": True,
            "pdf_page_size": "Letter",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["pdf_enabled"] is True
    assert payload["pdf_page_size"] == "Letter"


def test_config_rejects_invalid_pdf_page_size(client) -> None:
    _reset_client_config()
    response = client.put(
        "/api/config",
        json={
            "pdf_page_size": "TABLOID",
        },
    )
    assert response.status_code == 400
    assert "pdf_page_size" in str(response.json()["detail"])
