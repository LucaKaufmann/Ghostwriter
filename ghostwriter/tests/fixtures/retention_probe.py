"""Opt-in, synthetic characterization of scheduled digest cleanup.

Run from ghostwriter/: python tests/fixtures/retention_probe.py
This intentionally does not assert target behavior or join normal pytest collection.
"""

import asyncio
import importlib.util
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="retention-probe-") as temporary:
        root = Path(temporary)
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        os.chdir(root)  # Settings must not load a worktree or production .env.
        os.environ["DATA_DIR"] = str(root / "data")
        os.environ["OUTPUT_DIR"] = str(root / "output")
        os.environ["LOGS_DIR"] = str(root / "logs")

        from sqlalchemy import create_engine, select
        from sqlalchemy.orm import Session
        from sqlmodel import SQLModel

        import app.models  # noqa: F401 - register model tables
        from app.models.digest import Digest, DigestArticle
        from app.models.feed import Feed
        # Load this module without app.worker.__init__, which imports provider code.
        cleanup_path = Path(__file__).resolve().parents[2] / "app/worker/cleanup.py"
        spec = importlib.util.spec_from_file_location("retention_cleanup_probe", cleanup_path)
        assert spec is not None and spec.loader is not None
        cleanup = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cleanup)

        output_dir = root / "output"
        output_dir.mkdir()
        db_engine = create_engine(f"sqlite:///{root / 'probe.sqlite'}")
        SQLModel.metadata.create_all(db_engine)
        digest_id = uuid4()
        filename = f"synthetic_{digest_id.hex}.epub"
        epub = output_dir / filename
        pdf = output_dir / filename.replace(".epub", ".pdf")
        epub.write_bytes(b"synthetic epub")
        pdf.write_bytes(b"synthetic pdf")
        unrelated = output_dir / "unrelated.epub"
        unrelated.write_bytes(b"unrelated")

        with Session(db_engine) as session:
            feed = Feed(url=f"synthetic://probe/{uuid4()}", title="Synthetic")
            session.add(feed)
            session.flush()
            session.add(
                Digest(
                    id=digest_id,
                    filename=filename,
                    period="manual",
                    status="completed",
                    created_at=datetime.utcnow() - timedelta(days=60),
                )
            )
            session.add(
                DigestArticle(
                    digest_id=digest_id,
                    feed_id=feed.id,
                    title="Synthetic article",
                    url="synthetic://article",
                    mode="raw",
                    content="synthetic content",
                )
            )
            session.commit()

        original_engine = cleanup.engine
        original_settings = cleanup.get_settings
        cleanup.engine = db_engine
        cleanup.get_settings = lambda: SimpleNamespace(
            output_dir=str(output_dir), digest_retention_days=30
        )
        try:
            reported_deleted = asyncio.run(cleanup.cleanup_old_digests())
        finally:
            cleanup.engine = original_engine
            cleanup.get_settings = original_settings

        with Session(db_engine) as session:
            digest_exists = session.get(Digest, digest_id) is not None
            article_exists = session.scalar(
                select(DigestArticle).where(DigestArticle.digest_id == digest_id)
            ) is not None

        print(json.dumps({
            "reported_deleted": reported_deleted,
            "digest_exists": digest_exists,
            "article_exists": article_exists,
            "epub_exists": epub.exists(),
            "pdf_exists": pdf.exists(),
            "unrelated_exists": unrelated.exists(),
        }, sort_keys=True))


if __name__ == "__main__":
    main()
