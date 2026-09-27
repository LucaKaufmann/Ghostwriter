"""Durable feed change clock and mutation replay receipts."""

from datetime import datetime
from uuid import uuid4

from sqlmodel import Field, SQLModel


class FeedSyncClock(SQLModel, table=True):
    __tablename__ = "feed_sync_clock"

    id: int = Field(default=1, primary_key=True)
    version: int = Field(default=0)
    server_instance_id: str = Field(default_factory=lambda: str(uuid4()))


class FeedMutationReceipt(SQLModel, table=True):
    __tablename__ = "feed_mutation_receipts"

    op_id: str = Field(primary_key=True)
    payload_hash: str
    result_json: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
