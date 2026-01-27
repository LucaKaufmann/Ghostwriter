"""SeenArticle model for deduplication tracking."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlmodel import Field, Index, SQLModel


class SeenArticle(SQLModel, table=True):
    """
    SeenArticle entity for tracking processed articles.

    Used to prevent duplicate articles across digest runs.
    """

    __tablename__ = "seen_articles"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    feed_id: UUID = Field(foreign_key="feeds.id", index=True)
    guid: str = Field(index=True, description="RSS GUID or URL hash")
    url: str = Field(description="Original article URL")
    title: str = Field(description="Article title for debugging")
    seen_at: datetime = Field(
        default_factory=datetime.utcnow, description="First encountered"
    )

    __table_args__ = (Index("ix_seen_articles_feed_guid", "feed_id", "guid"),)
