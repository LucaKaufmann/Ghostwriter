"""Database initialization and session management."""

import os
from collections.abc import Generator

from sqlmodel import Session, SQLModel, create_engine

from app.core.config import get_settings
from app.models.wallabag_config import WallabagConfig  # noqa: F401 - ensure table creation


def get_database_url() -> str:
    """
    Get the SQLite database URL.

    Returns:
        SQLite connection string.
    """
    settings = get_settings()
    os.makedirs(settings.data_dir, exist_ok=True)
    return f"sqlite:///{settings.data_dir}/ghostwriter.db"


engine = create_engine(
    get_database_url(),
    echo=False,
    connect_args={"check_same_thread": False},
)


def init_db() -> None:
    """Initialize database tables and ensure indexes exist."""
    SQLModel.metadata.create_all(engine)

    # Add indexes that create_all won't apply to existing tables
    with engine.connect() as conn:
        conn.execute(
            __import__("sqlalchemy").text(
                "CREATE INDEX IF NOT EXISTS ix_digests_status ON digests (status)"
            )
        )

        # Add integration enabled columns (safe for existing DBs)
        for stmt in [
            "ALTER TABLE wallabag_config ADD COLUMN enabled BOOLEAN DEFAULT 1",
            "ALTER TABLE client_config ADD COLUMN newsletters_enabled BOOLEAN DEFAULT 1",
        ]:
            try:
                conn.execute(__import__("sqlalchemy").text(stmt))
            except Exception:
                pass  # Column already exists

        conn.commit()


def get_session() -> Generator[Session, None, None]:
    """
    Get a database session.

    Yields:
        SQLModel Session instance.
    """
    with Session(engine) as session:
        yield session
