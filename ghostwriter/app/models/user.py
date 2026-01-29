"""User model for authentication."""

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    """
    User account model.

    Stores user credentials and metadata for authentication.
    The first registered user is automatically an admin.
    """

    __tablename__ = "users"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    username: str = Field(index=True, unique=True, min_length=3, max_length=50)
    email: Optional[str] = Field(default=None, max_length=254)
    password_hash: str = Field(max_length=255)
    is_admin: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_login_at: Optional[datetime] = Field(default=None)


class UserCreate(SQLModel):
    """Schema for creating a new user."""

    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8, max_length=128)
    email: Optional[str] = Field(default=None, max_length=254)


class UserUpdate(SQLModel):
    """Schema for updating a user."""

    email: Optional[str] = Field(default=None, max_length=254)
    password: Optional[str] = Field(default=None, min_length=8, max_length=128)


class UserResponse(SQLModel):
    """Schema for user response (excludes sensitive data)."""

    id: UUID
    username: str
    email: Optional[str]
    is_admin: bool
    created_at: datetime
    last_login_at: Optional[datetime]


class LoginRequest(SQLModel):
    """Schema for login request."""

    username: str
    password: str


class LoginResponse(SQLModel):
    """Schema for login response."""

    access_token: str
    token_type: str = "bearer"
    user: UserResponse
