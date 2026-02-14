"""Manual cover uploads for digest EPUB generation."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class ManualCover(SQLModel, table=True):
    """Uploaded manual covers managed in Ghostwriter settings."""

    __tablename__ = "manual_covers"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(default="")
    file_name: str = Field(default="")
    media_type: str = Field(default="image/jpeg")
    size_bytes: int = Field(default=0, ge=0)
    is_active: bool = Field(default=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
