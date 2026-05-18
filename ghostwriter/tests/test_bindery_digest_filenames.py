"""Tests for digest output filename handling."""

import asyncio
from pathlib import Path

import pytest
from sqlmodel import Session, select

from app.core.config import Settings
from app.core.database import engine, init_db
from app.models.digest import Digest
from app.services.content_processor import ExtractedArticle
from app.services.epub_generator import EpubGenerator
from app.worker import bindery


class CompletingPipeline:
    """Minimal pipeline stub that clears the digest lock."""

    def __init__(self, digest_id):
        self.digest_id = digest_id

    async def run(self) -> None:
        with Session(engine) as session:
            digest = session.get(Digest, self.digest_id)
            if digest:
                digest.status = "completed"
                digest.stage = "completed"
                digest.locked_at = None
                session.add(digest)
                session.commit()


@pytest.mark.asyncio
async def test_generate_digest_uses_unique_filename_for_repeated_period(
    monkeypatch,
) -> None:
    init_db()
    with Session(engine) as session:
        running = session.exec(
            select(Digest).where(Digest.status == "processing")
        ).all()
        for digest in running:
            digest.status = "failed"
            digest.locked_at = None
            session.add(digest)
        session.commit()

    monkeypatch.setattr(bindery, "BinderyPipeline", CompletingPipeline)

    first_id = await bindery.generate_digest("manual")
    await asyncio.sleep(0)
    second_id = await bindery.generate_digest("manual")
    await asyncio.sleep(0)

    assert first_id is not None
    assert second_id is not None

    with Session(engine) as session:
        first = session.get(Digest, first_id)
        second = session.get(Digest, second_id)

    assert first is not None
    assert second is not None
    assert first.filename != second.filename
    assert first.filename.endswith(f"_{first_id.hex}.epub")
    assert second.filename.endswith(f"_{second_id.hex}.epub")


def test_epub_generator_writes_requested_output_filename(tmp_path: Path) -> None:
    generator = EpubGenerator(Settings(output_dir=str(tmp_path)))
    article = ExtractedArticle(
        guid="article-1",
        url="https://example.com/article-1",
        title="Article 1",
        content="Body",
        feed_title="Example",
    )

    output_path = generator.generate(
        [article],
        period="manual",
        output_filename="stored-digest-name.epub",
    )

    assert output_path == str(tmp_path / "stored-digest-name.epub")
    assert (tmp_path / "stored-digest-name.epub").exists()
