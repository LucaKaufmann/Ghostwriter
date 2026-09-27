"""The acknowledgement ledger exists on both upgrade and fresh bootstrap paths."""

import os
import subprocess
from pathlib import Path
from uuid import uuid4

import sqlalchemy as sa
from sqlmodel import Session, SQLModel, select

import app.models  # noqa: F401 - register the representative 026 schema
from app.models.digest import Digest
from app.models.feed import Feed
from app.models.source_acknowledgement import SourceAcknowledgement

ROOT = Path(__file__).resolve().parents[1]


def migrate(data_dir: Path) -> None:
    env = dict(os.environ, DATA_DIR=str(data_dir))
    subprocess.run(
        ["alembic", "-c", str(ROOT / "alembic.ini"), "upgrade", "027"],
        cwd=ROOT, env=env, check=True, capture_output=True, text=True,
    )


def test_receipt_table_upgrades_from_026_and_is_idempotent(tmp_path):
    assert "source_acknowledgements" in SQLModel.metadata.tables
    assert SourceAcknowledgement.__table__.c.digest_id.foreign_keys == set()
    tmp_path.mkdir(exist_ok=True)
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'ghostwriter.db'}")
    SQLModel.metadata.create_all(
        engine,
        tables=[
            table for table in SQLModel.metadata.sorted_tables
            if table.name != "source_acknowledgements"
        ],
    )
    feed_id, digest_id, receipt_id = uuid4(), uuid4(), uuid4()
    with Session(engine) as session:
        session.add(Feed(
            id=feed_id, url="https://example.test/feed.xml", title="Prior feed"
        ))
        session.add(Digest(
            id=digest_id, filename="prior.epub", period="manual",
            status="completed",
        ))
        session.commit()
    with engine.begin() as connection:
        connection.execute(sa.text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        connection.execute(sa.text("INSERT INTO alembic_version VALUES ('026')"))
    migrate(tmp_path)
    with Session(engine) as session:
        session.add(SourceAcknowledgement(
            id=receipt_id, digest_id=digest_id, provider="wallabag",
            source_identity="identity-hash", source_config_fingerprint="action-hash",
            external_item_id="7", action="archive_and_tag",
        ))
        session.commit()
    # Re-run the actual 027 upgrade against an existing 027 table, rather than
    # calling `upgrade head` at head (which would skip the migration body).
    with engine.begin() as connection:
        connection.execute(sa.text("UPDATE alembic_version SET version_num='026'"))
    migrate(tmp_path)
    with Session(engine) as session:
        assert session.get(Feed, feed_id).title == "Prior feed"
        assert session.get(Digest, digest_id).filename == "prior.epub"
        receipts = session.exec(select(SourceAcknowledgement)).all()
        assert len(receipts) == 1 and receipts[0].id == receipt_id
    with engine.connect() as connection:
        assert connection.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one() == "027"
        columns = {row[1] for row in connection.execute(sa.text("PRAGMA table_info(source_acknowledgements)"))}
        assert {"digest_id", "provider", "source_identity", "source_config_fingerprint", "external_item_id", "state"} <= columns
        indexes = {row[1] for row in connection.execute(sa.text("PRAGMA index_list(source_acknowledgements)"))}
        assert "ix_source_ack_state_created" in indexes


def test_receipt_table_exists_on_fresh_bootstrap(tmp_path):
    migrate(tmp_path)
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'ghostwriter.db'}")
    with engine.connect() as connection:
        # Fresh bootstrap stamps the current head after creating all model tables.
        assert connection.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one() == "028"
        assert sa.inspect(connection).has_table("source_acknowledgements")
