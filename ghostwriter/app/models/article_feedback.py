"""Article feedback model and API schemas."""

from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import Index, UniqueConstraint
from sqlmodel import Field, SQLModel

ArticleRating = Literal["up", "down"]


class ArticleFeedbackBase(SQLModel):
    """Base article feedback fields."""

    user_id: UUID | None = Field(default=None, foreign_key="users.id", index=True)
    article_id: UUID = Field(index=True)
    digest_id: UUID | None = Field(default=None, foreign_key="digests.id", index=True)
    rating: str | None = Field(default=None)
    read_duration_sec: int | None = Field(default=None, ge=0)
    bookmarked: bool = Field(default=False)
    shared: bool = Field(default=False)


class ArticleFeedback(ArticleFeedbackBase, table=True):
    """Article feedback row for explicit/implicit preference learning."""

    __tablename__ = "article_feedback"
    __table_args__ = (
        UniqueConstraint("user_id", "article_id", name="uq_article_feedback_user_article"),
        Index("ix_article_feedback_created_at", "created_at"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ArticleFeedbackUpsert(SQLModel):
    """Schema for creating/updating article feedback."""

    rating: ArticleRating
    read_duration_sec: int | None = Field(default=None, ge=0)
    bookmarked: bool | None = None
    shared: bool | None = None


class ArticleFeedbackRead(SQLModel):
    """Schema for reading article feedback."""

    article_id: UUID
    digest_id: UUID | None = None
    rating: ArticleRating | None = None
    read_duration_sec: int | None = None
    bookmarked: bool
    shared: bool
    created_at: datetime
    updated_at: datetime
