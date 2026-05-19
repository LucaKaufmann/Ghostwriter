"""Alembic environment configuration."""

import os
import sys
from logging.config import fileConfig

import sqlalchemy as sa
from sqlalchemy import engine_from_config, inspect, pool
from sqlmodel import SQLModel

from alembic import context

# Add the app directory to the path so we can import models
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import all models to ensure they're registered with SQLModel
from app.models.api_token import APIToken  # noqa: F401, E402
from app.models.article_feedback import ArticleFeedback  # noqa: F401, E402
from app.models.client_config import ClientConfig  # noqa: F401, E402
from app.models.client_settings import ClientSettings  # noqa: F401, E402
from app.models.digest import Digest, DigestArticle  # noqa: F401, E402
from app.models.feed import Feed  # noqa: F401, E402
from app.models.manual_cover import ManualCover  # noqa: F401, E402
from app.models.media_feed import MediaFeed  # noqa: F401, E402
from app.models.media_item import MediaItem  # noqa: F401, E402
from app.models.podcast_episode import PodcastEpisode  # noqa: F401, E402
from app.models.podcast_preferences import PodcastPreferences  # noqa: F401, E402
from app.models.schedule import Schedule  # noqa: F401, E402
from app.models.seen_article import SeenArticle  # noqa: F401, E402
from app.models.user import User  # noqa: F401, E402
from app.models.wallabag_config import WallabagConfig  # noqa: F401, E402

# this is the Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Use SQLModel's metadata for autogenerate support
target_metadata = SQLModel.metadata

LEGACY_BOOTSTRAP_REVISION = "004"
LEGACY_BOOTSTRAP_TABLE_NAMES = {
    "api_tokens",
    "client_config",
    "client_settings",
    "digest_articles",
    "digests",
    "feeds",
    "schedules",
    "seen_articles",
    "users",
    "wallabag_config",
}


def get_database_url() -> str:
    """Get the database URL from environment or default."""
    data_dir = os.environ.get("DATA_DIR", "/app/data")
    os.makedirs(data_dir, exist_ok=True)
    return f"sqlite:///{data_dir}/ghostwriter.db"


def has_application_tables(table_names: set[str]) -> bool:
    """Return whether any SQLModel application table already exists."""
    return bool(set(target_metadata.tables) & table_names)


def stamp_revision(connection: sa.Connection, revision: str) -> None:
    """Create alembic_version and stamp it with a specific revision."""
    connection.execute(
        sa.text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
    )
    connection.execute(
        sa.text("INSERT INTO alembic_version (version_num) VALUES (:v)"),
        {"v": revision},
    )


def create_legacy_bootstrap_tables(connection: sa.Connection) -> None:
    """Create only tables expected before the idempotent migration chain."""
    tables = [
        target_metadata.tables[name]
        for name in LEGACY_BOOTSTRAP_TABLE_NAMES
        if name in target_metadata.tables
    ]
    target_metadata.create_all(connection, tables=tables)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well. By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # Required for SQLite ALTER TABLE support
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    # Create a configuration dict with the database URL
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_database_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        # Fresh database: create all tables from models and stamp as current.
        # Migrations 001-005 are not fully idempotent (001 uses CREATE TABLE,
        # 002-005 assume client_config exists), so for a new database we skip
        # the migration chain entirely — create_all() produces the current schema.
        insp = inspect(connection)
        table_names = set(insp.get_table_names())
        if "alembic_version" not in table_names:
            if not has_application_tables(table_names):
                target_metadata.create_all(connection)
                # Stamp the current head revision directly (can't use command.stamp
                # from within env.py — it re-enters run_env and fails).
                stamp_revision(connection, context.script.get_current_head())
                connection.commit()
                return

            # Existing pre-Alembic databases have app tables but no version row.
            # Create missing legacy tables, then start after the non-idempotent
            # early revisions so consolidation migrations repair columns.
            create_legacy_bootstrap_tables(connection)
            stamp_revision(connection, LEGACY_BOOTSTRAP_REVISION)
            connection.commit()

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # Required for SQLite ALTER TABLE support
        )

        with context.begin_transaction():
            context.run_migrations()

        # SQLAlchemy 2.0 auto-begins transactions. Alembic's non-transactional
        # DDL mode (SQLite) does not commit, so we must commit explicitly to
        # persist both DDL changes and the alembic_version update.
        connection.commit()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
