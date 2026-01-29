"""API Token model for programmatic access."""

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class APIToken(SQLModel, table=True):
    """
    API Token model for programmatic access (mobile apps, scripts).

    Tokens are stored hashed (bcrypt). The full token is only shown once
    at creation time.
    """

    __tablename__ = "api_tokens"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", index=True)
    name: str = Field(max_length=100)  # e.g., "My iPhone", "Home Server"
    token_hash: str = Field(max_length=255)  # bcrypt hash of the token
    token_prefix: str = Field(max_length=16)  # First 8 chars for display (e.g., "gw_abc12...")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_used_at: Optional[datetime] = Field(default=None)
    revoked_at: Optional[datetime] = Field(default=None)


class APITokenCreate(SQLModel):
    """Schema for creating a new API token."""

    name: str = Field(min_length=1, max_length=100)


class APITokenResponse(SQLModel):
    """Schema for API token response (excludes hash)."""

    id: UUID
    name: str
    token_prefix: str
    created_at: datetime
    last_used_at: Optional[datetime]
    revoked_at: Optional[datetime]


class APITokenCreateResponse(SQLModel):
    """
    Schema for newly created API token.

    WARNING: The full token is only returned here, at creation time.
    It cannot be retrieved again.
    """

    id: UUID
    name: str
    token: str  # Full token - shown ONCE
    token_prefix: str
    created_at: datetime
