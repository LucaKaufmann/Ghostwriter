import json

from sqlmodel import Session

from app.core.config import Settings
from app.models.wallabag_config import WallabagConfig
from app.services.newsletter_service import NewsletterService
from app.services.wallabag_service import WallabagService


def test_newsletter_get_auth_url_writes_pending_state(tmp_path):
    settings = Settings(
        gmail_client_id="client-id",
        gmail_client_secret="client-secret",
        data_dir=str(tmp_path),
    )
    service = NewsletterService(settings)

    url = service.get_auth_url("https://example.com/callback")
    assert "accounts.google.com" in url
    assert "client_id=client-id" in url

    pending_file = tmp_path / "gmail_oauth_pending.json"
    assert pending_file.exists()

    pending = json.loads(pending_file.read_text())
    assert pending["redirect_uri"] == "https://example.com/callback"
    assert "state" in pending
    assert "code_verifier" in pending


def test_wallabag_from_db_configured(client):
    from app.core.database import engine

    with Session(engine) as session:
        session.add(
            WallabagConfig(
                url="https://wallabag.example.com",
                client_id="id",
                client_secret="secret",
                username="user",
                password="pass",
            )
        )
        session.commit()

        service = WallabagService.from_db_or_settings(session)
        assert service.is_configured is True
