"""One-off ownership survives episode deletion without guessing old owners."""

import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import sqlalchemy as sa

ROOT = Path(__file__).resolve().parents[1]


def alembic(data_dir: Path, command: str, revision: str) -> None:
    result = subprocess.run(
        [str(Path(sys.executable).with_name("alembic")), "-c", str(ROOT / "alembic.ini"),
         command, revision],
        cwd=ROOT, env={**os.environ, "DATA_DIR": str(data_dir)},
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr


def test_027_upgrade_backfills_only_unambiguous_one_off_owners(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'ghostwriter.db'}")
    owner, other, missing = (uuid4().hex for _ in range(3))
    digest_ids = {name: uuid4().hex for name in (
        "owned", "conflict", "null_owner", "malformed", "zero_articles",
        "normal", "bad_sibling", "missing_user",
    )}
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE users (id CHAR(32) PRIMARY KEY)")
        connection.exec_driver_sql(
            "CREATE TABLE digests (id CHAR(32) PRIMARY KEY, filename VARCHAR, "
            "period VARCHAR, status VARCHAR)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE podcast_episodes (id CHAR(32) PRIMARY KEY, "
            "trigger VARCHAR, digest_ids JSON, user_id CHAR(32))"
        )
        connection.exec_driver_sql("CREATE TABLE alembic_version (version_num VARCHAR(32))")
        connection.execute(sa.text("INSERT INTO alembic_version VALUES ('027')"))
        for user_id in (owner, other):
            connection.execute(sa.text("INSERT INTO users (id) VALUES (:id)"), {"id": user_id})
        for name, digest_id in digest_ids.items():
            connection.execute(sa.text(
                "INSERT INTO digests (id, filename, period, status) "
                "VALUES (:id, :filename, 'manual', 'completed')"
            ), {"id": digest_id, "filename": f"{name}.epub"})

        def episode(name, user_id, refs, trigger="one_off"):
            connection.execute(sa.text(
                "INSERT INTO podcast_episodes (id, trigger, digest_ids, user_id) "
                "VALUES (:id, :trigger, :refs, :owner)"
            ), {"id": uuid4().hex, "trigger": trigger,
                "refs": json.dumps(refs) if isinstance(refs, list) else refs,
                "owner": user_id})

        episode("owned", owner, [str(uuid4()), str(uuid4())])
        episode("owned", owner, [digest_ids["owned"]])
        episode("owned", owner, [str(uuid4()), digest_ids["owned"]])
        episode("conflict", owner, [digest_ids["conflict"]])
        episode("conflict", other, [digest_ids["conflict"]])
        episode("null_owner", owner, [digest_ids["null_owner"]])
        episode("null_owner", None, [digest_ids["null_owner"]])
        episode("malformed", owner, "not-json")
        episode("zero_articles", owner, [digest_ids["zero_articles"]])
        episode("normal", owner, [digest_ids["normal"]], trigger="manual")
        episode("bad_sibling", owner, [digest_ids["bad_sibling"], "bad-id"])
        episode("missing_user", missing, [digest_ids["missing_user"]])

    alembic(tmp_path, "upgrade", "028")
    with engine.connect() as connection:
        owners = {row[0]: row[1] for row in connection.execute(sa.text(
            "SELECT filename, one_off_owner_id FROM digests"
        ))}
        assert owners["owned.epub"] == owner
        assert owners["zero_articles.epub"] == owner
        assert owners["bad_sibling.epub"] == owner
        assert all(owners[f"{name}.epub"] is None for name in (
            "conflict", "null_owner", "malformed", "normal", "missing_user",
        ))
    # Re-run the body on an already-upgraded database, then exercise no-op downgrade.
    with engine.begin() as connection:
        connection.execute(sa.text("UPDATE alembic_version SET version_num='027'"))
    alembic(tmp_path, "upgrade", "028")
    alembic(tmp_path, "downgrade", "027")
    with engine.connect() as connection:
        columns = {row[1] for row in connection.execute(sa.text("PRAGMA table_info(digests)"))}
        assert "one_off_owner_id" in columns


def test_fresh_upgrade_has_nullable_one_off_owner(tmp_path):
    alembic(tmp_path, "upgrade", "head")
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'ghostwriter.db'}")
    with engine.connect() as connection:
        assert connection.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one() == "028"
        columns = {row[1]: row for row in connection.execute(sa.text("PRAGMA table_info(digests)"))}
        assert columns["one_off_owner_id"][3] == 0
