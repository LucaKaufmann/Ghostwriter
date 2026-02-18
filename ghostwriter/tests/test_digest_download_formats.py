"""Tests for digest download endpoint format support."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from sqlmodel import Session

from app.core.database import engine
from app.models.digest import Digest, DigestArticle
from app.models.feed import Feed


def test_download_digest_by_id_epub(client) -> None:
    output_dir = Path(os.environ["OUTPUT_DIR"])
    output_dir.mkdir(parents=True, exist_ok=True)

    digest_id = uuid4()
    filename = f"{uuid4()}.epub"
    (output_dir / filename).write_bytes(b"epub-bytes")

    with Session(engine) as session:
        session.add(
            Digest(
                id=digest_id,
                filename=filename,
                period="manual",
                status="completed",
                stage="completed",
                created_at=datetime.utcnow(),
            )
        )
        session.commit()

    response = client.get(f"/api/digests/{digest_id}/download?format=epub")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/epub+zip"
    assert response.content == b"epub-bytes"

    digests_response = client.get("/api/digests")
    assert digests_response.status_code == 200
    first_digest = digests_response.json()[0]
    assert first_digest["available_formats"] == ["epub", "pdf"]


def test_download_digest_by_id_pdf_generates_on_demand(client) -> None:
    output_dir = Path(os.environ["OUTPUT_DIR"])
    output_dir.mkdir(parents=True, exist_ok=True)

    digest_id = uuid4()
    feed_id = uuid4()
    filename = f"{uuid4()}.epub"
    (output_dir / filename).write_bytes(b"epub-bytes")

    with Session(engine) as session:
        session.add(
            Feed(
                id=feed_id,
                url=f"https://example.com/{feed_id}",
                title="Test Feed",
                mode="raw",
                max_articles=10,
            )
        )
        session.add(
            Digest(
                id=digest_id,
                filename=filename,
                period="manual",
                status="completed",
                stage="completed",
                created_at=datetime.utcnow(),
            )
        )
        session.add(
            DigestArticle(
                digest_id=digest_id,
                feed_id=feed_id,
                title="PDF Article",
                url="https://example.com/article",
                mode="raw",
                word_count=42,
                ai_failed=False,
                processing_ms=1,
                content="Simple paragraph content.",
                author="Tester",
                feed_title="Test Feed",
                sort_order=0,
                content_type="article",
            )
        )
        session.commit()

    response = client.get(f"/api/digests/{digest_id}/download?format=pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")

    pdf_name = filename.rsplit(".", 1)[0] + ".pdf"
    assert (output_dir / pdf_name).exists()
