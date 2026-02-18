"""Tests for PDF digest generation."""

from datetime import datetime
from pathlib import Path

from app.core.config import Settings
from app.services.content_processor import ExtractedArticle
from app.services.pdf_generator import PdfGenerator


def _article(
    *,
    guid: str,
    title: str,
    feed_title: str,
    content: str = "Plain paragraph content for PDF rendering.",
    content_type: str = "article",
) -> ExtractedArticle:
    return ExtractedArticle(
        guid=guid,
        url=f"https://example.com/{guid}",
        title=title,
        content=content,
        author="Author",
        word_count=120,
        is_summary=False,
        feed_title=feed_title,
        content_type=content_type,
    )


def test_pdf_generator_creates_pdf_file(tmp_path: Path) -> None:
    settings = Settings(output_dir=str(tmp_path))
    generator = PdfGenerator(settings=settings)

    path = generator.generate(
        articles=[
            _article(guid="a1", title="Article One", feed_title="Tech"),
            _article(guid="a2", title="Article Two", feed_title="World"),
        ],
        period="manual",
        date=datetime(2026, 2, 18, 8, 0, 0),
    )

    output = Path(path)
    assert output.exists()
    assert output.suffix == ".pdf"
    assert output.name == "2026-02-18_manual.pdf"
    assert output.read_bytes().startswith(b"%PDF")


def test_pdf_generator_supports_media_sections(tmp_path: Path) -> None:
    settings = Settings(output_dir=str(tmp_path))
    generator = PdfGenerator(settings=settings)

    path = generator.generate(
        articles=[_article(guid="r1", title="Regular", feed_title="News")],
        media_articles=[
            _article(
                guid="m1",
                title="Podcast Episode",
                feed_title="Pod Feed",
                content_type="podcast",
            )
        ],
        period="morning",
        date=datetime(2026, 2, 18, 8, 0, 0),
        page_size="INVALID",
    )

    output = Path(path)
    assert output.exists()
    assert output.read_bytes().startswith(b"%PDF")
