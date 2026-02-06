import asyncio
import base64
from email.message import EmailMessage

from app.core.config import Settings
from app.services.newsletter_service import NewsletterService


def _build_raw_email(
    *,
    subject: str,
    sender: str,
    plain_text: str | None = None,
    html_text: str | None = None,
    extra_headers: dict[str, str] | None = None,
) -> str:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    if extra_headers:
        for key, value in extra_headers.items():
            msg[key] = value

    if plain_text is not None and html_text is not None:
        msg.set_content(plain_text)
        msg.add_alternative(html_text, subtype="html")
    elif plain_text is not None:
        msg.set_content(plain_text)
    elif html_text is not None:
        msg.set_content(html_text, subtype="html")
    else:
        msg.set_content("")

    return base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii").rstrip("=")


def test_clean_newsletter_html_ignores_comments(tmp_path) -> None:
    service = NewsletterService(Settings(data_dir=str(tmp_path)))
    raw_html = """
    <html>
      <body>
        <!-- tracking comment -->
        <div>
          Hello <span>world</span>
          <!-- another comment -->
        </div>
      </body>
    </html>
    """

    cleaned = service._clean_newsletter_html(raw_html)

    assert "Hello" in cleaned
    assert "world" in cleaned
    assert "<!--" not in cleaned


def test_parse_email_prefers_plain_text_from_raw(tmp_path) -> None:
    service = NewsletterService(Settings(data_dir=str(tmp_path)))
    msg = {
        "id": "abc123",
        "raw": _build_raw_email(
            subject="Daily Brief",
            sender="Briefing <digest@example.com>",
            plain_text="Plain intro\n\nPlain second paragraph",
            html_text="<html><body><p>HTML fallback</p></body></html>",
            extra_headers={"List-Unsubscribe": "<mailto:unsubscribe@example.com>"},
        ),
    }

    article = service._parse_email(msg)

    assert article is not None
    assert "<p>Plain intro</p>" in article.content
    assert "HTML fallback" not in article.content
    assert article.word_count >= 4


def test_parse_email_falls_back_to_html_if_plain_missing(tmp_path) -> None:
    service = NewsletterService(Settings(data_dir=str(tmp_path)))
    msg = {
        "id": "def456",
        "raw": _build_raw_email(
            subject="HTML Newsletter",
            sender="Updates <updates@example.com>",
            html_text="""
            <html>
              <body>
                <!-- tracking -->
                <div>Hello <span>world</span></div>
              </body>
            </html>
            """,
        ),
    }

    article = service._parse_email(msg)

    assert article is not None
    assert "Hello" in article.content
    assert "world" in article.content
    assert "<!--" not in article.content


def test_fetch_newsletters_continues_when_one_message_parse_fails(
    monkeypatch,
    tmp_path,
) -> None:
    service = NewsletterService(Settings(data_dir=str(tmp_path)))
    good_raw = _build_raw_email(
        subject="Good newsletter",
        sender="Good Sender <good@example.com>",
        plain_text="Good content",
    )

    class _FakeResponse:
        def __init__(self, payload: dict) -> None:
            self._payload = payload

        def raise_for_status(self) -> None:
            return

        def json(self) -> dict:
            return self._payload

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            return

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url: str, headers=None, params=None) -> _FakeResponse:
            if url.endswith("/labels"):
                return _FakeResponse(
                    {"labels": [{"id": "LBL_1", "name": "Ghostwriter"}]}
                )
            if url.endswith("/messages"):
                return _FakeResponse({"messages": [{"id": "bad"}, {"id": "good"}]})
            if url.endswith("/messages/bad"):
                return _FakeResponse({"id": "bad", "raw": good_raw})
            if url.endswith("/messages/good"):
                return _FakeResponse({"id": "good", "raw": good_raw})
            raise AssertionError(f"Unexpected URL: {url}")

    async def _fake_access_token() -> str:
        return "token"

    original_parse = service._parse_email

    def _parse_with_failure(msg: dict):
        if msg.get("id") == "bad":
            raise ValueError("simulated parse failure")
        return original_parse(msg)

    monkeypatch.setattr(service, "_get_access_token", _fake_access_token)
    monkeypatch.setattr(service, "_parse_email", _parse_with_failure)
    monkeypatch.setattr(
        "app.services.newsletter_service.httpx.AsyncClient",
        _FakeAsyncClient,
    )

    articles, message_ids = asyncio.run(service.fetch_newsletters())

    assert len(articles) == 1
    assert message_ids == ["good"]
    assert articles[0].title == "Good newsletter"
