"""Feed sync schema upgrade and restore identity integration."""

import os
import socket
import sqlite3
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlmodel import Session, create_engine, select

from app.core.database import engine, get_session
from app.models.feed import Feed
from app.services.feed_sync import _begin_write, _clock

ROOT = Path(__file__).resolve().parents[1]


def _alembic(data_dir: Path, target: str) -> None:
    subprocess.run(["alembic", "-c", str(ROOT / "alembic.ini"), "upgrade", target],
                   cwd=ROOT, env={**os.environ, "DATA_DIR": str(data_dir)},
                   check=True, capture_output=True, text=True)


def test_026_backfill_and_fresh_schema(tmp_path):
    previous = tmp_path / "previous"
    previous.mkdir()
    db = sa.create_engine(f"sqlite:///{previous / 'ghostwriter.db'}")
    with db.begin() as conn:
        conn.execute(sa.text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        conn.execute(sa.text("INSERT INTO alembic_version VALUES ('025')"))
        conn.execute(sa.text("CREATE TABLE feeds (id CHAR(32) PRIMARY KEY, url VARCHAR NOT NULL UNIQUE, "
                             "title VARCHAR NOT NULL, is_active BOOLEAN NOT NULL, mode VARCHAR NOT NULL, "
                             "max_articles INTEGER NOT NULL, deleted_at DATETIME, "
                             "created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)"))
        columns = {row[1] for row in conn.execute(sa.text("PRAGMA table_info(feeds)"))}
        assert "version" not in columns
        for name in ("https://example.com/a", "synthetic://newsletter", "https://example.com/b"):
            conn.execute(sa.text("INSERT INTO feeds (id,url,title,is_active,mode,max_articles,created_at,updated_at) "
                                 "VALUES (:id,:url,'Title',1,'raw',5,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"),
                         {"id": uuid4().hex, "url": name})
    _alembic(previous, "026")
    with db.connect() as conn:
        rows = conn.execute(sa.text("SELECT url,version FROM feeds ORDER BY url")).all()
        versions = dict(rows)
        assert versions["synthetic://newsletter"] == 0
        assert sorted([versions["https://example.com/a"], versions["https://example.com/b"]]) == [1, 2]
        identity = conn.execute(sa.text("SELECT server_instance_id FROM feed_sync_clock WHERE id=1")).scalar_one()
        assert identity
        assert "feed_mutation_receipts" in sa.inspect(conn).get_table_names()
    # Re-run 026 against its already-upgraded schema, with durable state present.
    with db.begin() as conn:
        conn.execute(sa.text("INSERT INTO feed_mutation_receipts(op_id,payload_hash,result_json,created_at) "
                             "VALUES ('replay-test','hash','{}',CURRENT_TIMESTAMP)"))
        conn.execute(sa.text("UPDATE alembic_version SET version_num='025'"))
    _alembic(previous, "026")
    with db.connect() as conn:
        assert dict(conn.execute(sa.text("SELECT url,version FROM feeds")).all()) == versions
        assert conn.execute(sa.text("SELECT server_instance_id FROM feed_sync_clock WHERE id=1")).scalar_one() == identity
        assert conn.execute(sa.text("SELECT result_json FROM feed_mutation_receipts WHERE op_id='replay-test'")).scalar_one() == "{}"
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    _alembic(fresh, "head")
    fresh_engine = sa.create_engine(f"sqlite:///{fresh / 'ghostwriter.db'}")
    with fresh_engine.connect() as conn:
        assert "version" in {row[1] for row in conn.execute(sa.text("PRAGMA table_info(feeds)"))}
        assert "feed_sync_clock" in sa.inspect(conn).get_table_names()
    with Session(fresh_engine) as session:
        _begin_write(session)
        assert _clock(session).version == 0
        session.commit()
    with pytest.raises(sa.exc.IntegrityError), fresh_engine.begin() as conn:
        conn.execute(sa.text("INSERT INTO feed_sync_clock (id,version,server_instance_id) VALUES (2,0,'bad')"))


def test_restored_backup_rotated_identity_rejects_old_client(client, monkeypatch, tmp_path):
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, port, *a, **k: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.215.14", port))
    ])
    old_instance = client.get("/api/feeds/changes-v2").json()["server_instance_id"]
    data_dir = tmp_path / "restore"
    data_dir.mkdir()
    restored_file = data_dir / "ghostwriter.db"
    source = sqlite3.connect(engine.url.database)
    target = sqlite3.connect(restored_file)
    source.backup(target)
    source.close()
    target.close()
    feed_url = f"https://example.com/{uuid4()}.xml"
    operation = {"op_id": str(uuid4()), "url": feed_url, "kind": "upsert",
                 "base_version": None,
                 "fields": {"title": "Old", "is_active": True,
                            "mode": "raw", "max_articles": 5}}
    accepted = client.post("/api/feeds/mutations-v2", json={
        "server_instance_id": old_instance, "mutations": [operation],
    })
    assert accepted.status_code == 200
    assert accepted.json()["results"][0]["status"] == "applied"
    command = subprocess.run([sys.executable, "-m", "app.cli.rotate_sync_identity"],
                             cwd=ROOT, env={**os.environ, "DATA_DIR": str(data_dir)},
                             check=True, capture_output=True, text=True)
    new_instance = command.stdout.strip()
    assert new_instance and new_instance != old_instance
    restored_engine = create_engine(f"sqlite:///{restored_file}", connect_args={"check_same_thread": False})

    def restored_session():
        with Session(restored_engine) as session:
            yield session

    client.app.dependency_overrides[get_session] = restored_session
    try:
        response = client.post("/api/feeds/mutations-v2", json={
            "server_instance_id": old_instance,
            "mutations": [operation],
        })
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "server_changed"
        with Session(restored_engine) as session:
            assert session.exec(select(Feed).where(Feed.url == feed_url)).first() is None
    finally:
        client.app.dependency_overrides.pop(get_session, None)
