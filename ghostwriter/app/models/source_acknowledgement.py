"""Durable intent to acknowledge a published source item."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Index, UniqueConstraint
from sqlmodel import Field, SQLModel


class SourceAcknowledgement(SQLModel, table=True):
    __tablename__ = "source_acknowledgements"
    __table_args__ = (
        UniqueConstraint(
            "digest_id", "provider", "source_identity", "source_config_fingerprint",
            "external_item_id", "action", name="uq_source_ack_item",
        ),
        Index("ix_source_ack_state_created", "state", "created_at"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    # Intentionally no FK: an acknowledgement outlives local digest deletion.
    digest_id: UUID = Field(index=True)
    provider: str
    source_identity: str
    source_config_fingerprint: str
    external_item_id: str
    action: str
    state: str = Field(default="pending")
    attempt_count: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_attempt_at: datetime | None = None
    completed_at: datetime | None = None
    last_error_code: str | None = None
