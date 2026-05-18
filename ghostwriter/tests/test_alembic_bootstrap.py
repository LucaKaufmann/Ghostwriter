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


def column_names(conn: sa.Connection, table: str) -> set[str]:
    result = conn.execute(sa.text(f"PRAGMA table_info({table})"))
    return {row[1] for row in result}


def test_unversioned_existing_database_runs_repair_migrations(
    monkeypatch,
    tmp_path,
) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("DATA_DIR", str(data_dir))

    engine = sa.create_engine(f"sqlite:///{data_dir / 'ghostwriter.db'}")
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                """
                CREATE TABLE client_config (
                    id VARCHAR(32) NOT NULL PRIMARY KEY,
                    min_word_count INTEGER NOT NULL DEFAULT 0,
                    morning_hour INTEGER NOT NULL DEFAULT 7,
                    morning_minute INTEGER NOT NULL DEFAULT 0,
                    noon_hour INTEGER NOT NULL DEFAULT 12,
                    noon_minute INTEGER NOT NULL DEFAULT 0,
                    evening_hour INTEGER NOT NULL DEFAULT 18,
                    evening_minute INTEGER NOT NULL DEFAULT 0,
                    timezone VARCHAR NOT NULL DEFAULT 'UTC',
                    summarize_sh_whisper_model VARCHAR(32) NOT NULL DEFAULT 'tiny.en',
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        conn.execute(
            sa.text(
                """
                INSERT INTO client_config (id, summarize_sh_whisper_model)
                VALUES ('config', 'tiny.en')
                """
            )
        )
        conn.execute(
            sa.text(
                """
                CREATE TABLE feeds (
                    id VARCHAR(32) NOT NULL PRIMARY KEY,
                    url VARCHAR NOT NULL,
                    title VARCHAR NOT NULL,
                    is_active BOOLEAN NOT NULL DEFAULT 1,
                    mode VARCHAR NOT NULL DEFAULT 'raw',
                    max_articles INTEGER NOT NULL DEFAULT 10,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )

    head = run_alembic("heads").stdout.split()[0]
    run_alembic("upgrade", "head")

    with engine.connect() as conn:
        client_columns = column_names(conn, "client_config")
        assert "whisper_model" in client_columns
        assert "newsletters_enabled" in client_columns
        assert "media_processing_interval_hours" in client_columns
        assert "pdf_enabled" in client_columns
        assert "cover_overlay_enabled" in client_columns
        assert "deleted_at" in column_names(conn, "feeds")

        whisper_model = conn.execute(
            sa.text("SELECT whisper_model FROM client_config WHERE id = 'config'")
        ).scalar_one()
        assert whisper_model == "tiny.en"

        version = conn.execute(sa.text("SELECT version_num FROM alembic_version"))
        assert version.scalar_one() == head
