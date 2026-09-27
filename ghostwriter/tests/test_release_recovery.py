"""Disposable upgrade/restore checks; fixture artifacts are not real audio."""

import hashlib
import json
import os
import shutil
import site
import sqlite3
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[1]
RELEASE_SQL = Path(__file__).parent / "fixtures" / "release_021.sql"
VOLUMES = ("data", "output", "logs", "ollama")
ARTIFACTS = {
    "data/gmail_token.json": b'{"fixture_only": true}',
    "output/fixture-edition.epub": b"synthetic epub preservation sentinel",
    "output/fixture-edition.pdf": b"synthetic pdf preservation sentinel",
    "output/podcasts/00000000-0000-0000-0000-000000000004.mp3": b"synthetic audio preservation sentinel",
    "logs/fixture.log": b"Synthetic diagnostic only\n",
    "ollama/models/fixture.model": b"optional sidecar volume sentinel",
}


def environment(root):
    env = dict(os.environ)
    env.update(
        DATA_DIR=str(root / "data"),
        OUTPUT_DIR=str(root / "output"),
        LOGS_DIR=str(root / "logs"),
        SCHEDULE_ENABLED="false",
        PYTHONPATH=os.pathsep.join([*site.getsitepackages(), str(ROOT)]),
    )
    for volume in VOLUMES:
        (root / volume).mkdir(parents=True, exist_ok=True)
    return env


def alembic(root, *args, check=True):
    return subprocess.run(
        [str(Path(sys.executable).with_name("alembic")), "-c", str(ROOT / "alembic.ini"), *args],
        cwd=ROOT,
        env=environment(root),
        check=check,
        capture_output=True,
        text=True,
        timeout=60,
    )


def rows(root):
    with sqlite3.connect(root / "data" / "ghostwriter.db") as db:
        return {
            "feed": db.execute("SELECT id,url,title,max_articles FROM feeds").fetchall(),
            "digest": db.execute("SELECT id,filename,status,article_count FROM digests").fetchall(),
            "article": db.execute("SELECT id,digest_id,feed_id,content FROM digest_articles").fetchall(),
            "seen": db.execute("SELECT feed_id,guid,url,seen_at FROM seen_articles").fetchall(),
            "episode": db.execute("SELECT id,digest_ids,article_ids,status,audio_path FROM podcast_episodes").fetchall(),
            "config": db.execute("SELECT id,min_word_count,timezone FROM client_config").fetchall(),
            "preferences": db.execute("SELECT id,enabled,style,preferred_length_minutes FROM podcast_preferences").fetchall(),
        }


def artifact_hashes(root):
    return {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest()
        for name in ARTIFACTS
    }


def assert_current(root):
    head = alembic(root, "heads").stdout.split()[0]
    with sqlite3.connect(root / "data" / "ghostwriter.db") as db:
        assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert db.execute("SELECT version_num FROM alembic_version").fetchone() == (head,)
        columns = {row[1] for row in db.execute("PRAGMA table_info(podcast_episodes)")}
        assert {"generation_preferences", "title", "chapters"} <= columns
        preference_columns = {row[1] for row in db.execute("PRAGMA table_info(podcast_preferences)")}
        assert "elevenlabs_expressiveness" in preference_columns
        for row in db.execute("SELECT elevenlabs_expressiveness FROM podcast_preferences"):
            assert row == ("natural",)


def startup_check(root, *, has_edition=False):
    """Run actual lifespan/health/reader routes in a separate, offline process."""
    program = r'''
import socket
import sys
from app.core.config import Settings
Settings.model_config = {**Settings.model_config, "env_file": None}
def block_ip(function):
    def guarded(sock, *args, **kwargs):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            raise AssertionError("Readiness must not access external sources")
        return function(sock, *args, **kwargs)
    return guarded
def no_dns(*args, **kwargs):
    raise AssertionError("Readiness must not resolve external sources")
for name in ("connect", "connect_ex", "sendto", "sendmsg"):
    if hasattr(socket.socket, name):
        setattr(socket.socket, name, block_ip(getattr(socket.socket, name)))
for name in ("getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr", "getnameinfo"):
    setattr(socket, name, no_dns)
from fastapi.testclient import TestClient
from app.main import app
with TestClient(app) as client:
    assert client.get("/api/health").status_code == 200
    if sys.argv[1] == "edition":
        response = client.get("/api/digests/00000000-0000-0000-0000-000000000002/articles")
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["article_count"] == 1
        assert payload["articles"][0]["content"] == "Synthetic content for restore verification."
'''
    subprocess.run(
        [sys.executable, "-c", program, "edition" if has_edition else "empty"],
        cwd=root,
        env=environment(root),
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_fresh_upgrade_is_repeatable(tmp_path):
    alembic(tmp_path, "upgrade", "head")
    assert_current(tmp_path)
    startup_check(tmp_path)
    first = rows(tmp_path)
    alembic(tmp_path, "upgrade", "head")
    startup_check(tmp_path)
    assert_current(tmp_path)
    assert rows(tmp_path) == first


def test_release_021_upgrade_and_stopped_volume_restore(tmp_path):
    live, backup, restored = (tmp_path / name for name in ("live", "backup", "restored"))
    environment(live)
    with sqlite3.connect(live / "data" / "ghostwriter.db") as db:
        db.executescript(RELEASE_SQL.read_text())
        # Prove this fixture predates the new columns, rather than stamping HEAD 021.
        columns = {row[1] for row in db.execute("PRAGMA table_info(podcast_episodes)")}
        assert not {"generation_preferences", "title", "chapters"} & columns
        assert db.execute("SELECT version_num FROM alembic_version").fetchone() == ("021",)
    for name, content in ARTIFACTS.items():
        path = live / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    before_rows, before_artifacts = rows(live), artifact_hashes(live)
    # No connection/process is open while taking this coordinated stopped backup.
    for volume in VOLUMES:
        shutil.copytree(live / volume, backup / volume)
    alembic(live, "upgrade", "head")
    startup_check(live, has_edition=True)
    alembic(live, "upgrade", "head")
    startup_check(live, has_edition=True)
    assert_current(live)
    assert rows(live) == before_rows
    assert artifact_hashes(live) == before_artifacts
    # Restore the PRE-upgrade backup into a different storage root, then upgrade.
    for volume in VOLUMES:
        shutil.copytree(backup / volume, restored / volume)
    alembic(restored, "upgrade", "head")
    startup_check(restored, has_edition=True)
    assert_current(restored)
    assert rows(restored) == before_rows
    assert artifact_hashes(restored) == before_artifacts
    # Container mount paths remain /app/output even when host volume location changes.
    audio_path = before_rows["episode"][0][-1]
    assert audio_path.startswith("/app/output/")
    assert (restored / "output" / audio_path.removeprefix("/app/output/")).exists()


def _offline_feed_mutation(root, instance_id, operation):
    """Exercise the v2 HTTP route without startup jobs or external network."""
    program = r'''
import json
import socket
import sys
from app.core.config import Settings
Settings.model_config = {**Settings.model_config, "env_file": None}
def block_ip(function):
    def guarded(sock, *args, **kwargs):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            raise AssertionError("Release fixture must not contact external sources")
        return function(sock, *args, **kwargs)
    return guarded
def no_dns(*args, **kwargs):
    raise AssertionError("Release fixture must not resolve external sources")
def synthetic_dns(host, port, *args, **kwargs):
    assert host == "example.com", "Unexpected DNS request in release fixture"
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.215.14", port))]
for name in ("connect", "connect_ex", "sendto", "sendmsg"):
    if hasattr(socket.socket, name):
        setattr(socket.socket, name, block_ip(getattr(socket.socket, name)))
for name in ("gethostbyname", "gethostbyname_ex", "gethostbyaddr", "getnameinfo"):
    setattr(socket, name, no_dns)
socket.getaddrinfo = synthetic_dns
from fastapi.testclient import TestClient
from app.main import app
client = TestClient(app)
response = client.post("/api/feeds/mutations-v2", json={
    "server_instance_id": sys.argv[1], "mutations": [json.loads(sys.argv[2])]
})
print(json.dumps({"status": response.status_code, "body": response.json()}))
client.close()
'''
    result = subprocess.run(
        [sys.executable, "-c", program, instance_id, json.dumps(operation)],
        cwd=ROOT, env=environment(root), check=True, capture_output=True,
        text=True, timeout=60,
    )
    return json.loads(result.stdout)


def test_current_026_028_stopped_restore_keeps_ack_and_rotates_identity(tmp_path):
    live, backup, restored = (tmp_path / name for name in ("live", "backup", "restored"))
    alembic(live, "upgrade", "head")
    assert_current(live)
    assert alembic(live, "heads").stdout.split()[0] == "028"
    # The migration has created the clock table; the operational command seeds
    # its identity before this disposable instance accepts writes.
    rotate = [sys.executable, "-m", "app.cli.rotate_sync_identity"]
    subprocess.run(rotate, cwd=ROOT, env=environment(live), check=True,
                   capture_output=True, text=True, timeout=60)
    acknowledgement_id = uuid4().hex
    with sqlite3.connect(live / "data" / "ghostwriter.db") as db:
        instance_id = db.execute("SELECT server_instance_id FROM feed_sync_clock WHERE id=1").fetchone()[0]
        db.execute(
            "INSERT INTO source_acknowledgements "
            "(id,digest_id,provider,source_identity,source_config_fingerprint,"
            "external_item_id,action,state,attempt_count,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)",
            (acknowledgement_id, uuid4().hex, "gmail", uuid4().hex * 2,
             uuid4().hex * 2, "fixture-message", "mark_read", "pending", 0),
        )
        expected_ack = db.execute(
            "SELECT id,provider,source_identity,external_item_id,state,attempt_count "
            "FROM source_acknowledgements WHERE id=?", (acknowledgement_id,),
        ).fetchone()
    # No process or connection is open while all volumes are copied together.
    for volume in VOLUMES:
        shutil.copytree(live / volume, backup / volume)
    feed_url = f"https://example.com/{uuid4()}.xml"
    operation = {
        "op_id": str(uuid4()), "url": feed_url, "kind": "upsert",
        "base_version": None,
        "fields": {"title": "Post-backup edit", "is_active": True,
                   "mode": "raw", "max_articles": 5},
    }
    accepted = _offline_feed_mutation(live, instance_id, operation)
    assert accepted["status"] == 200
    assert accepted["body"]["results"][0]["status"] == "applied"
    for volume in VOLUMES:
        shutil.copytree(backup / volume, restored / volume)
    alembic(restored, "upgrade", "head")
    rotated = subprocess.run(
        rotate, cwd=ROOT, env=environment(restored), check=True,
        capture_output=True, text=True, timeout=60,
    ).stdout.strip()
    assert rotated and rotated != instance_id
    rejected = _offline_feed_mutation(restored, instance_id, operation)
    assert rejected["status"] == 409
    assert rejected["body"]["detail"]["code"] == "server_changed"
    with sqlite3.connect(restored / "data" / "ghostwriter.db") as db:
        assert db.execute("SELECT id,provider,source_identity,external_item_id,state,attempt_count "
                          "FROM source_acknowledgements WHERE id=?", (acknowledgement_id,)).fetchone() == expected_ack
        assert db.execute("SELECT id FROM feeds WHERE url=?", (feed_url,)).fetchone() is None
        assert db.execute("SELECT op_id FROM feed_mutation_receipts WHERE op_id=?",
                          (operation["op_id"],)).fetchone() is None
    assert_current(restored)


def test_unknown_revision_fails_without_replacing_database(tmp_path):
    environment(tmp_path)
    with sqlite3.connect(tmp_path / "data" / "ghostwriter.db") as db:
        db.executescript(RELEASE_SQL.read_text())
        db.execute("UPDATE alembic_version SET version_num='future_unsupported'")
    before = rows(tmp_path)
    failed = alembic(tmp_path, "upgrade", "head", check=False)
    assert failed.returncode != 0
    assert "future_unsupported" in failed.stderr
    assert rows(tmp_path) == before


@pytest.mark.parametrize("migration_status", [0, 42])
def test_entrypoint_only_starts_server_after_migration_success(tmp_path, migration_status):
    executables = tmp_path / "bin"
    executables.mkdir()
    marker = tmp_path / "server-started"
    for name, body in {
        "alembic": f"exit {migration_status}\n",
        "python": 'touch "$READINESS_SERVER_MARKER"\n',
    }.items():
        executable = executables / name
        executable.write_text("#!/bin/sh\n" + body)
        executable.chmod(0o755)
    script = (ROOT / "entrypoint.sh").read_text()
    assert script.count("cd /app") == 1
    # Substitute the container's mount point; execute all control flow unchanged.
    script = script.replace("cd /app", 'cd "$READINESS_APP_DIR"')
    result = subprocess.run(
        ["sh", "-c", script],
        env={**os.environ, "PATH": f"{executables}:/usr/bin:/bin",
             "READINESS_APP_DIR": str(tmp_path), "READINESS_SERVER_MARKER": str(marker)},
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == migration_status
    assert marker.exists() == (migration_status == 0)
