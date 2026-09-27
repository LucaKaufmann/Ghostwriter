"""Rotate the feed server instance UUID after restoring a database backup.

Run with the server stopped: python -m app.cli.rotate_sync_identity
"""

from sqlmodel import Session

from app.core.database import engine
from app.services.feed_sync import rotate_identity


def main() -> None:
    with Session(engine) as session:
        print(rotate_identity(session))


if __name__ == "__main__":
    main()
