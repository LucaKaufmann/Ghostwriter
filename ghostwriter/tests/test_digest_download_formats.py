"""Tests for digest download endpoint format support."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from sqlmodel import Session
from sqlmodel import delete as sql_delete

from app.core.database import engine
from app.models.client_config import ClientConfig
from app.models.digest import Digest, DigestArticle
from app.models.feed import Feed


def _set_pdf_config(enabled: bool, page_size: str = "A4") -> None:
    with Session(engine) as session:
        session.exec(sql_delete(ClientConfig))
        session.add(ClientConfig(pdf_enabled=enabled, pdf_page_size=page_size))
        session.commit()


def test_download_digest_by_id_epub(client) -> None:
    _set_pdf_config(enabled=False)

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
    filename_response = client.get(f"/api/digests/{filename}")
    assert filename_response.status_code == 200
    assert filename_response.content == response.content
    assert response.headers["content-length"] == str(len(response.content))
    assert response.headers["accept-ranges"] == "bytes"
    assert filename_response.headers["content-length"] == str(len(response.content))

    for url in (f"/api/digests/{digest_id}/download", f"/api/digests/{filename}"):
        single = client.get(url, headers={"Range": "bytes=1-3"})
        assert single.status_code == 206
        assert single.content == b"pub"
        assert single.headers["content-range"] == "bytes 1-3/10"
        assert single.headers["content-length"] == "3"
        suffix = client.get(url, headers={"Range": "bytes=-5"})
        assert suffix.status_code == 206
        assert suffix.content == b"bytes"
        opened = client.get(url, headers={"Range": "bytes=5-"})
        assert opened.status_code == 206
        assert opened.content == b"bytes"
        invalid = client.get(url, headers={"Range": "bytes=999-"})
        assert invalid.status_code == 416
        assert invalid.headers["content-range"] == "bytes */10"
        multiple = client.get(url, headers={"Range": "bytes=0-1,5-6"})
        assert multiple.status_code == 206
        assert multiple.headers["content-type"].startswith("multipart/byteranges")
        assert b"Content-Range: bytes 0-1/10" in multiple.content
        assert b"Content-Range: bytes 5-6/10" in multiple.content
        assert multiple.headers["content-length"] == str(len(multiple.content))
        stale = client.get(url, headers={"Range": "bytes=1-3", "If-Range": '"stale"'})
        assert stale.status_code == 200
        assert stale.content == b"epub-bytes"
        matching = client.get(
            url, headers={"Range": "bytes=1-3", "If-Range": response.headers["etag"]}
        )
        assert matching.status_code == 206
        assert matching.content == b"pub"

    digests_response = client.get("/api/digests")
    assert digests_response.status_code == 200
    first_digest = digests_response.json()[0]
    assert first_digest["available_formats"] == ["epub"]


def test_download_digest_by_id_pdf_generates_on_demand(client) -> None:
    _set_pdf_config(enabled=True, page_size="A4")

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
    assert response.headers["content-length"] == str(len(response.content))
    partial = client.get(
        f"/api/digests/{digest_id}/download?format=pdf",
        headers={"Range": "bytes=0-3"},
    )
    assert partial.status_code == 206
    assert partial.content == b"%PDF"
    assert partial.headers["content-length"] == "4"
    assert partial.headers["content-range"] == f"bytes 0-3/{len(response.content)}"
