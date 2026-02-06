"""Tests for feed-grouped digest ordering and EPUB chapters."""

from dataclasses import dataclass
from datetime import datetime
import os
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

os.environ.setdefault("DATA_DIR", "/tmp/ghostwriter_test")
os.environ.setdefault("OUTPUT_DIR", "/tmp/ghostwriter_test_output")
os.environ.setdefault("API_KEY", "")

from app.core.config import Settings
from app.models.feed import Feed
from app.services.content_processor import ExtractedArticle
from app.services.epub_generator import EpubGenerator
from app.worker.bindery import BinderyPipeline


@dataclass
class ParsedStub:
    """Minimal parsed-article stub used for ordering tests."""

    guid: str


def test_order_fetched_articles_groups_by_feed_order() -> None:
    """Fetched articles are grouped deterministically by configured feed order."""
    feed_a = Feed(url="https://a.example/rss", title="Feed A")
    feed_b = Feed(url="https://b.example/rss", title="Feed B")

    fetched = [
        (feed_b, ParsedStub(guid="b-1")),
        (feed_a, ParsedStub(guid="a-1")),
        (feed_b, ParsedStub(guid="b-2")),
    ]

    ordered = BinderyPipeline._order_fetched_articles_by_feed(
        fetched,
        {feed_a.id: 0, feed_b.id: 1},
    )

    assert [article.guid for _, article in ordered] == ["a-1", "b-1", "b-2"]


def test_order_extracted_articles_restores_fetch_order() -> None:
    """Extracted articles return to original fetch order despite async completion order."""
    feed_a = Feed(url="https://a.example/rss", title="Feed A")
    feed_b = Feed(url="https://b.example/rss", title="Feed B")

    extracted_out_of_order = [
        (
            feed_b,
            ExtractedArticle(
                guid="b-1",
                url="https://b.example/1",
                title="B1",
                content="Body",
                feed_title="Feed B",
            ),
        ),
        (
            feed_a,
            ExtractedArticle(
                guid="a-1",
                url="https://a.example/1",
                title="A1",
                content="Body",
                feed_title="Feed A",
            ),
        ),
    ]

    order_map = {
        (feed_a.id, "a-1"): 0,
        (feed_b.id, "b-1"): 1,
    }

    ordered = BinderyPipeline._order_extracted_articles(
        extracted_out_of_order,
        order_map,
    )

    assert [article.guid for _, article in ordered] == ["a-1", "b-1"]


def test_epub_generator_creates_feed_chapters_with_article_subchapters(tmp_path: Path) -> None:
    """EPUB TOC should include feed chapters containing article entries."""
    settings = Settings(output_dir=str(tmp_path))
    generator = EpubGenerator(settings)

    articles = [
        ExtractedArticle(
            guid="a-1",
            url="https://a.example/1",
            title="Article A1",
            content="<p>A1 content</p>",
            feed_title="Feed A",
        ),
        ExtractedArticle(
            guid="a-2",
            url="https://a.example/2",
            title="Article A2",
            content="<p>A2 content</p>",
            feed_title="Feed A",
        ),
        ExtractedArticle(
            guid="b-1",
            url="https://b.example/1",
            title="Article B1",
            content="<p>B1 content</p>",
            feed_title="Feed B",
        ),
    ]

    epub_path = generator.generate(
        articles=articles,
        period="manual",
        date=datetime(2026, 2, 1),
    )

    with zipfile.ZipFile(epub_path, "r") as zf:
        names = zf.namelist()
        assert any(name.endswith("feed_001_feed-a.xhtml") for name in names)
        assert any(name.endswith("feed_002_feed-b.xhtml") for name in names)
        assert any(name.endswith("feed_001_article_001_feed-a.xhtml") for name in names)
        assert any(name.endswith("feed_001_article_002_feed-a.xhtml") for name in names)
        assert any(name.endswith("feed_002_article_001_feed-b.xhtml") for name in names)

        toc_name = next(name for name in names if name.endswith("toc.ncx"))
        toc_xml = zf.read(toc_name)

    root = ET.fromstring(toc_xml)
    ns = {"ncx": "http://www.daisy.org/z3986/2005/ncx/"}
    labels = [
        element.text
        for element in root.findall(".//ncx:navLabel/ncx:text", ns)
        if element.text
    ]

    assert "Feed A" in labels
    assert "Feed B" in labels
    assert "Article A1" in labels
    assert "Article A2" in labels
    assert "Article B1" in labels

    feed_a_index = labels.index("Feed A")
    feed_b_index = labels.index("Feed B")
    assert feed_a_index < feed_b_index
