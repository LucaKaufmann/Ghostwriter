"""Tests for markdown conversion helpers."""

from app.services.markdown_utils import markdown_to_html_basic


def test_markdown_to_html_basic_headings_and_paragraphs():
    markdown = "### Newsy opener\nLine one.\n\nLine two."
    html = markdown_to_html_basic(markdown)
    assert "<h3>Newsy opener</h3>" in html
    assert "<p>Line one.</p>" in html
    assert "<p>Line two.</p>" in html


def test_markdown_to_html_basic_lists_and_inline_formatting():
    markdown = "- First item\n- **Second** item with *emphasis*"
    html = markdown_to_html_basic(markdown)
    assert "<ul>" in html
    assert "<li>First item</li>" in html
    assert "<li><strong>Second</strong> item with <em>emphasis</em></li>" in html
