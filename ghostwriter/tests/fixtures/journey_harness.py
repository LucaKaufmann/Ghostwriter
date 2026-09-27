"""Deterministic external boundaries for a real local reading/listening journey."""

from __future__ import annotations

import subprocess
from pathlib import Path

from sqlmodel import Session

from app.core.config import get_settings
from app.core.database import engine
from app.models.client_config import ClientConfig
from app.models.feed import Feed
from app.services.outbound_fetch import FetchedResource
from app.services.podcast_service import AudioGenerationResult, podcast_service
from app.worker.bindery import BinderyPipeline

ARTICLE_TITLE = "Synthetic Observatory"
ARTICLE_TEXT = (
    "The synthetic observatory records a clear sky and a quiet city. "
    "Its carefully written report gives readers a complete, harmless story. "
) * 12


def install(
    monkeypatch, output_dir: Path, *, article_url: str = "https://fixture.invalid/observatory"
) -> dict[str, int]:
    """Replace only remote RSS/extraction/AI/TTS boundaries, never persistence/rendering."""
    calls = {"audio": 0}

    async def fetch_feed(url, **kwargs):
        assert url == "https://fixture.invalid/feed.xml"
        assert kwargs["kind"] == "feed"
        xml = (
            "<?xml version='1.0'?><rss version='2.0'><channel>"
            "<title>Fixture News</title><link>https://fixture.invalid/</link>"
            "<description>Synthetic fixture</description><item>"
            f"<title>{ARTICLE_TITLE}</title><link>{article_url}</link>"
            "<guid>journey-observatory-1</guid>"
            f"<description>{ARTICLE_TEXT}</description>"
            "<author>Fixture Writer</author></item></channel></rss>"
        )
        return FetchedResource(
            final_url=url,
            content_type="application/rss+xml",
            encoding="utf-8",
            data=xml.encode(),
        )

    async def extract_content(self, url):
        assert url == article_url
        return f"<p>{ARTICLE_TEXT}</p>"

    async def no_cover(self, **kwargs):
        return None

    async def script(articles, prefs, **kwargs):
        assert articles and ARTICLE_TITLE == articles[0].title
        return (
            "[HOST_A]: The observatory records a clear sky.\n"
            "[HOST_B]: Its report is ready to read and hear.\n"
            "[HOST_A]: The city is quiet.\n"
            "[HOST_B]: The report was written for readers.\n"
            "[HOST_A]: Its details remain available.\n"
            "[HOST_B]: That concludes our story."
        )

    async def audio(episode_id, segments, prefs, chapters=None):
        calls["audio"] += 1
        if calls["audio"] == 1:
            raise RuntimeError("Synthetic provider interruption")
        path = output_dir / "podcasts" / f"journey-{episode_id}.mp3"
        path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i",
             "anullsrc=r=22050:cl=mono", "-t", "61", "-q:a", "9",
             "-y", str(path)],
            check=True,
            timeout=20,
        )
        return AudioGenerationResult(
            audio_path=str(path),
            audio_size_bytes=path.stat().st_size,
            duration_seconds=61,
            synthesized_chars=sum(len(segment.text) for segment in segments),
        )

    monkeypatch.setattr("app.services.content_processor.fetch_resource", fetch_feed)
    monkeypatch.setattr(
        "app.services.content_processor.ContentProcessor.extract_content",
        extract_content,
    )
    monkeypatch.setattr(BinderyPipeline, "_generate_cover_image", no_cover)
    monkeypatch.setattr(podcast_service, "generate_script", script)
    monkeypatch.setattr(podcast_service, "generate_audio", audio)

    with Session(engine) as session:
        session.add(Feed(url="https://fixture.invalid/feed.xml", title="Fixture News"))
        session.add(ClientConfig(pdf_enabled=True, cover_enabled=False))
        session.commit()
    assert Path(get_settings().output_dir) == output_dir
    return calls
