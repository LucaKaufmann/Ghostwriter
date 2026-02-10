"""Database initialization and session management."""

import os
from collections.abc import Generator

from sqlmodel import Session, SQLModel, create_engine

from app.core.config import get_settings
from app.models.wallabag_config import WallabagConfig  # noqa: F401 - ensure table creation
import app.models  # noqa: F401  # ensure all SQLModel tables are registered


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
    """Initialize database tables.

    Creates any missing tables from SQLModel metadata. Schema alterations
    (new columns, indexes, nullable changes) are handled by Alembic migrations.
    """
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    """
    Get a database session.

    Yields:
        SQLModel Session instance.
    """
    with Session(engine) as session:
        yield session
