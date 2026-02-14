"""Tests for digest content text-to-HTML formatting."""

from app.services.digest_content_formatter import format_digest_content_to_html


def test_preserves_existing_html():
    html = "<p>Hello</p><h2>World</h2>"
    assert format_digest_content_to_html(html) == html


def test_splits_dense_plain_text_into_multiple_paragraphs():
    text = (
        "This is a very long paragraph with several sentences that should be broken "
        "into multiple paragraphs for readability. It keeps going to ensure the "
        "splitter has enough content to work with. Another sentence adds more length "
        "and context for realistic digest content. One more sentence makes sure we "
        "cross the paragraph length threshold."
    )
    rendered = format_digest_content_to_html(text)
    assert rendered.count("<p>") >= 2


def test_detects_inline_heading_and_markdown_list():
    text = """Key Themes:
The release focused on reliability and performance improvements.

- Faster startup
- Better caching
- Lower memory usage"""
    rendered = format_digest_content_to_html(text)
    assert "<h3>Key Themes</h3>" in rendered
    assert "<ul>" in rendered
    assert "<li>Faster startup</li>" in rendered


def test_parses_markdown_heading():
    text = """## Market Overview
Risk sentiment improved across major indexes."""
    rendered = format_digest_content_to_html(text)
    assert "<h2>Market Overview</h2>" in rendered
    assert "<p>Risk sentiment improved across major indexes.</p>" in rendered
