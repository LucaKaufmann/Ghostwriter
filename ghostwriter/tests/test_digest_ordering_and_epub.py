"""Tests for feed-grouped digest ordering and EPUB chapters."""

import base64
from dataclasses import dataclass
from datetime import datetime
import io
import logging
import os
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

import httpx
from PIL import Image
import pytest

os.environ.setdefault("DATA_DIR", "/tmp/ghostwriter_test")
os.environ.setdefault("OUTPUT_DIR", "/tmp/ghostwriter_test_output")
os.environ.setdefault("API_KEY", "")

from app.core.config import Settings
from app.models.feed import Feed
from app.services.content_processor import ExtractedArticle
from app.services.cover_image_service import CoverImage, CoverImageService, CoverOverlayMetadata
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

def test_epub_generator_embeds_generated_cover_image(tmp_path: Path) -> None:
    """Generated cover image should be embedded and referenced by the cover page."""
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
    ]

    # 1x1 transparent PNG.
    png_data = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4"
        "//8/AwAI/AL+X4xL9QAAAABJRU5ErkJggg=="
    )
    cover_image = CoverImage(
        data=png_data,
        media_type="image/png",
        provider="gpt-image-1",
    )

    epub_path = generator.generate(
        articles=articles,
        period="manual",
        date=datetime(2026, 2, 1),
        cover_image=cover_image,
    )

    with zipfile.ZipFile(epub_path, "r") as zf:
        names = zf.namelist()
        assert any(name.endswith("images/cover.png") for name in names)

        cover_name = next(name for name in names if name.endswith("cover.xhtml"))
        cover_html = zf.read(cover_name).decode("utf-8")
        assert 'src="images/cover.png"' in cover_html

        opf_name = next(name for name in names if name.endswith("content.opf"))
        opf_xml = zf.read(opf_name)

    opf_root = ET.fromstring(opf_xml)
    ns = {"opf": "http://www.idpf.org/2007/opf"}

    cover_manifest = opf_root.find(".//opf:manifest/opf:item[@id='cover-img']", ns)
    assert cover_manifest is not None
    assert cover_manifest.get("href") == "images/cover.png"
    assert cover_manifest.get("properties") == "cover-image"

    cover_meta = opf_root.find(".//opf:metadata/opf:meta[@name='cover']", ns)
    assert cover_meta is not None
    assert cover_meta.get("content") == "cover-img"

    guide_cover_ref = opf_root.find(".//opf:guide/opf:reference[@type='cover']", ns)
    assert guide_cover_ref is not None
    assert guide_cover_ref.get("href") == "cover.xhtml"


def test_cover_image_service_normalizes_cover_to_5_8_jpeg() -> None:
    """Generated cover images should be normalized to compact 5:8 JPEG output."""
    service = CoverImageService()

    source_image = Image.new("RGB", (1200, 1200), color=(30, 30, 30))
    with io.BytesIO() as source_bytes:
        source_image.save(source_bytes, format="PNG")
        original = CoverImage(
            data=source_bytes.getvalue(),
            media_type="image/png",
            provider="nano-banana",
        )

    normalized = service._normalize_cover_image(original)
    assert normalized is not None
    assert normalized.media_type == "image/jpeg"
    assert len(normalized.data) <= 500 * 1024

    with Image.open(io.BytesIO(normalized.data)) as normalized_img:
        assert normalized_img.size == (960, 1536)


def test_epub_cover_file_name_normalizes_media_type_parameters() -> None:
    """Cover image extension mapping should ignore media-type parameters."""
    assert EpubGenerator._cover_image_file_name("image/jpeg; charset=binary") == "images/cover.jpg"


def test_cover_image_service_extract_source_labels_mixed_sources() -> None:
    """Source label extraction should deterministically reflect the digest content mix."""
    service = CoverImageService()
    articles = [
        ExtractedArticle(
            guid="n-1",
            url="https://news.example/1",
            title="News item",
            content="Body",
            feed_title="Tech Feed",
            content_type="article",
        ),
        ExtractedArticle(
            guid="w-1",
            url="https://wallabag.example/1",
            title="Wallabag item",
            content="Body",
            feed_title="Wallabag",
            content_type="article",
        ),
        ExtractedArticle(
            guid="nl-1",
            url="https://mail.google.com/1",
            title="Newsletter item",
            content="Body",
            feed_title="Newsletter",
            content_type="article",
        ),
        ExtractedArticle(
            guid="p-1",
            url="https://pod.example/1",
            title="Podcast item",
            content="Body",
            feed_title="Podcast",
            content_type="podcast",
        ),
        ExtractedArticle(
            guid="y-1",
            url="https://youtube.com/watch?v=1",
            title="YouTube item",
            content="Body",
            feed_title="Youtube",
            content_type="youtube",
        ),
    ]

    labels = service._extract_source_labels(articles)

    assert labels == ["News", "Wallabag", "Newsletter", "Podcast", "YouTube"]


def test_cover_image_service_prompt_requests_overlay_safe_space() -> None:
    """Prompt should reserve clean layout areas for deterministic metadata overlays."""
    service = CoverImageService()
    articles = [
        ExtractedArticle(
            guid="a-1",
            url="https://news.example/1",
            title="Headline one",
            content="Body",
            feed_title="Tech Feed",
            content_type="article",
        ),
        ExtractedArticle(
            guid="w-1",
            url="https://wallabag.example/1",
            title="Read-later item",
            content="Body",
            feed_title="Wallabag",
            content_type="article",
        ),
    ]

    prompt = service._build_prompt(
        period="morning",
        date=datetime(2026, 2, 14),
        articles=articles,
        prompt_suffix="",
    )

    assert "Do not render any readable text or letters" in prompt
    assert "negative space near the top and bottom" in prompt
    assert "Included source types: News, Wallabag." in prompt


def test_cover_image_service_overlay_metadata_changes_output_bytes() -> None:
    """Applying deterministic overlay metadata should alter encoded cover output."""
    service = CoverImageService()
    source_image = Image.new("RGB", (1200, 1200), color=(40, 40, 40))
    with io.BytesIO() as source_bytes:
        source_image.save(source_bytes, format="PNG")
        original = CoverImage(
            data=source_bytes.getvalue(),
            media_type="image/png",
            provider="gpt-image-1",
        )

    plain = service._normalize_cover_image(original)
    with_overlay = service._normalize_cover_image(
        original,
        overlay_metadata=CoverOverlayMetadata(
            title="Epilogue Digest",
            subtitle="2026-02-14 · Morning",
            sources=("News", "Newsletter"),
        ),
    )

    assert plain is not None
    assert with_overlay is not None
    assert plain.data != with_overlay.data


@pytest.mark.asyncio
async def test_cover_image_service_openai_payload_for_gpt_image(monkeypatch) -> None:
    """OpenAI cover request should match gpt-image-1 supported payload fields."""
    settings = Settings(openai_api_key="sk-test")
    service = CoverImageService(settings)
    captured_payload: dict = {}
    encoded = base64.b64encode(b"image-bytes").decode("utf-8")

    class _FakeResponse:
        def raise_for_status(self) -> None:
            return

        def json(self) -> dict:
            return {"data": [{"b64_json": encoded}]}

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            return

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, _url: str, headers=None, json=None) -> _FakeResponse:
            captured_payload["headers"] = headers
            captured_payload["json"] = json
            return _FakeResponse()

        async def get(self, _url: str):
            raise AssertionError("URL fetch path should not be used for gpt-image-1 responses")

    monkeypatch.setattr(
        "app.services.cover_image_service.httpx.AsyncClient",
        _FakeAsyncClient,
    )

    cover = await service._generate_openai(prompt="test prompt", quality="medium")

    assert cover is not None
    assert cover.data == b"image-bytes"
    assert cover.media_type == "image/png"
    assert captured_payload["json"]["model"] == "gpt-image-1"
    assert captured_payload["json"]["quality"] == "medium"
    assert "response_format" not in captured_payload["json"]


@pytest.mark.asyncio
async def test_cover_image_service_openai_http_error_logs_details(
    monkeypatch,
    caplog,
) -> None:
    """HTTP failures should log OpenAI status and response snippet for debugging."""
    settings = Settings(openai_api_key="sk-test")
    service = CoverImageService(settings)
    response = httpx.Response(
        status_code=400,
        request=httpx.Request("POST", "https://api.openai.com/v1/images/generations"),
        json={"error": {"message": "Unsupported parameter: response_format"}},
    )

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            return

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, _url: str, headers=None, json=None):
            return response

    monkeypatch.setattr(
        "app.services.cover_image_service.httpx.AsyncClient",
        _FakeAsyncClient,
    )

    with caplog.at_level(logging.WARNING):
        cover = await service._generate_openai(prompt="test prompt", quality="low")

    assert cover is None
    assert "OpenAI cover generation failed with status 400" in caplog.text
    assert "Unsupported parameter: response_format" in caplog.text


def test_epub_generator_formats_plain_text_content(tmp_path: Path) -> None:
    """Plain text chapter content should be expanded into structured HTML."""
    settings = Settings(output_dir=str(tmp_path))
    generator = EpubGenerator(settings)

    article = ExtractedArticle(
        guid="a-1",
        url="https://a.example/1",
        title="Structured Output",
        content=(
            "Section Highlights:\n"
            "This is a dense paragraph that should be broken into readable chunks. "
            "It contains several sentences to trigger paragraph splitting for EPUB output. "
            "Another sentence keeps the block long enough for formatting heuristics."
        ),
        feed_title="Feed A",
    )

    epub_path = generator.generate(
        articles=[article],
        period="manual",
        date=datetime(2026, 2, 1),
    )

    with zipfile.ZipFile(epub_path, "r") as zf:
        chapter_name = next(
            name for name in zf.namelist() if name.endswith("feed_001_article_001_feed-a.xhtml")
        )
        chapter_html = zf.read(chapter_name).decode("utf-8")

    assert "<h3>Section Highlights</h3>" in chapter_html
    assert chapter_html.count("<p>") >= 2
