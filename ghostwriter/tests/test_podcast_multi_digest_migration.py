import subprocess
from pathlib import Path

import sqlalchemy as sa

ROOT = Path(__file__).resolve().parents[1]


def run_alembic(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["alembic", "-c", str(ROOT / "alembic.ini"), *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def test_revision_018_drops_digest_id_constraints(monkeypatch, tmp_path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("DATA_DIR", str(data_dir))

    engine = sa.create_engine(f"sqlite:///{data_dir / 'ghostwriter.db'}")
    with engine.begin() as conn:
        conn.execute(
            sa.text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        )
        conn.execute(
            sa.text("INSERT INTO alembic_version (version_num) VALUES ('017')")
        )
        conn.execute(sa.text("CREATE TABLE users (id VARCHAR NOT NULL PRIMARY KEY)"))
        conn.execute(sa.text("CREATE TABLE digests (id VARCHAR NOT NULL PRIMARY KEY)"))
        conn.execute(sa.text("INSERT INTO users (id) VALUES ('user-1')"))
        conn.execute(sa.text("INSERT INTO digests (id) VALUES ('digest-1')"))
        conn.execute(
            sa.text(
                """
                CREATE TABLE podcast_episodes (
                    id VARCHAR NOT NULL PRIMARY KEY,
                    digest_id VARCHAR NOT NULL,
                    user_id VARCHAR,
                    script TEXT,
                    audio_path VARCHAR,
                    audio_size_bytes INTEGER,
                    duration_seconds INTEGER,
                    article_ids JSON NOT NULL DEFAULT '[]',
                    article_count INTEGER NOT NULL DEFAULT 0,
                    generation_cost_cents INTEGER,
                    status VARCHAR NOT NULL DEFAULT 'pending',
                    error_message VARCHAR,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    started_at DATETIME,
                    completed_at DATETIME,
                    CONSTRAINT ck_podcast_episodes_status
                        CHECK (status IN ('pending', 'generating_script', 'generating_audio', 'ready', 'failed')),
                    FOREIGN KEY(digest_id) REFERENCES digests (id),
                    FOREIGN KEY(user_id) REFERENCES users (id),
                    CONSTRAINT uq_podcast_episodes_digest_id UNIQUE (digest_id)
                )
                """
            )
        )
        conn.execute(
            sa.text(
                "CREATE INDEX ix_podcast_episodes_digest_id "
                "ON podcast_episodes (digest_id)"
            )
        )
        conn.execute(
            sa.text(
                "CREATE INDEX ix_podcast_episodes_user_id ON podcast_episodes (user_id)"
            )
        )
        conn.execute(
            sa.text(
                "CREATE INDEX ix_podcast_episodes_status ON podcast_episodes (status)"
            )
        )
        conn.execute(
            sa.text(
                """
                INSERT INTO podcast_episodes (id, digest_id, user_id, status)
                VALUES ('episode-1', 'digest-1', 'user-1', 'ready')
                """
            )
        )

    run_alembic("upgrade", "018")

    with engine.connect() as conn:
        columns = {
            row[1]
            for row in conn.execute(sa.text("PRAGMA table_info(podcast_episodes)"))
        }
        assert "digest_id" not in columns
        assert "digest_ids" in columns

        row = conn.execute(
            sa.text(
                "SELECT digest_ids, trigger "
                "FROM podcast_episodes WHERE id = 'episode-1'"
            )
        ).one()
        assert row.digest_ids == '["digest-1"]'
        assert row.trigger == "manual"

        foreign_keys = conn.execute(
            sa.text("PRAGMA foreign_key_list(podcast_episodes)")
        ).fetchall()
        assert all(foreign_key[3] != "digest_id" for foreign_key in foreign_keys)

        indexes = conn.execute(
            sa.text("PRAGMA index_list(podcast_episodes)")
        ).fetchall()
        for index in indexes:
            index_columns = conn.execute(
                sa.text(f"PRAGMA index_info({index[1]})")
            ).fetchall()
            assert all(index_column[2] != "digest_id" for index_column in index_columns)

        create_sql = conn.execute(
            sa.text(
                "SELECT sql FROM sqlite_master "
                "WHERE type = 'table' AND name = 'podcast_episodes'"
            )
        ).scalar_one()
        assert "uq_podcast_episodes_digest_id" not in create_sql
