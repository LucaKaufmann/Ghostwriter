import zipfile
from datetime import datetime

from app.core.config import Settings
from app.services.content_processor import ExtractedArticle
from app.services.epub_generator import EpubGenerator


def _read_epub_file(epub_path: str, suffix: str) -> str:
    with zipfile.ZipFile(epub_path) as zf:
        name = next(n for n in zf.namelist() if n.endswith(suffix))
        return zf.read(name).decode("utf-8")


def test_epub_generator_creates_sections_and_escapes(tmp_path):
    settings = Settings(output_dir=str(tmp_path))
    generator = EpubGenerator(settings)

    articles = [
        ExtractedArticle(
            guid="a1",
            url="https://example.com/a1",
            title="Bad <script>alert(1)</script>",
            content="Hello world",
            author="Author",
            word_count=2,
            is_summary=True,
            ai_failed=True,
        )
    ]
    saved_articles = [
        ExtractedArticle(
            guid="s1",
            url="https://example.com/s1",
            title="Saved",
            content="Saved content",
            author=None,
            word_count=2,
            is_summary=False,
            ai_failed=False,
        )
    ]
    newsletter_articles = [
        ExtractedArticle(
            guid="n1",
            url="https://example.com/n1",
            title="Newsletter",
            content="<p><strong>Hi</strong></p>",
            author="Sender",
            word_count=1,
            is_summary=False,
            ai_failed=False,
        )
    ]

    epub_path = generator.generate(
        articles=articles,
        period="morning",
        date=datetime(2025, 1, 1),
        saved_articles=saved_articles,
        newsletter_articles=newsletter_articles,
    )

    chapter = _read_epub_file(epub_path, "chapter_001.xhtml")
    assert "AI Summary" in chapter
    assert "AI fallback" in chapter
    assert "<script>" not in chapter

    newsletter = _read_epub_file(epub_path, "newsletter_000.xhtml")
    assert "<strong>Hi</strong>" in newsletter
