from app.core.config import Settings
from app.services.newsletter_service import NewsletterService


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
