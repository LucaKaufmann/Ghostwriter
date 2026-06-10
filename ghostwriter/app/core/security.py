"""Authentication and security utilities."""

import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session, select

from app.core.config import Settings, get_settings
from app.core.database import get_session

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)


def _get_token_from_request(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None,
) -> Optional[str]:
    """
    Extract authentication token from request.

    Checks in order:
    1. Authorization: Bearer <token>
    2. X-API-Key header
    """
    # Bearer token from Authorization header
    if credentials and credentials.credentials:
        return credentials.credentials

    # X-API-Key header
    api_key_header = request.headers.get("x-api-key")
    if api_key_header:
        return api_key_header

    return None


def _is_jwt_token(token: str) -> bool:
    """Check if a token looks like a JWT (has 3 dot-separated parts)."""
    parts = token.split(".")
    return len(parts) == 3


def _is_api_token(token: str) -> bool:
    """Check if a token looks like an API token (starts with gw_)."""
    return token.startswith("gw_")


async def verify_api_key(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    settings: Settings = Depends(get_settings),
) -> None:
    """
    Verify authentication from the Authorization header.

    Supports:
    - JWT tokens (from web UI login)
    - API tokens (gw_xxx format, from mobile apps)
    - Legacy API_KEY env var (deprecated, for backward compatibility)

    If no API_KEY is configured and no users exist, authentication is disabled
    (LAN-only mode for initial setup).
    """
    # Import here to avoid circular imports
    from app.core.auth import decode_access_token, get_token_prefix, verify_api_token
    from app.models.api_token import APIToken
    from app.models.user import User

    session = next(get_session())

    # Check if any users exist
    has_users = session.exec(select(User)).first() is not None

    # If no users and no legacy API_KEY, allow unauthenticated access (setup mode)
    if not has_users and not settings.api_key:
        return

    # Get token from request
    token = _get_token_from_request(request, credentials)

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Try JWT token first
    if _is_jwt_token(token):
        payload = decode_access_token(token)
        if payload:
            user_id = payload.get("sub")
            if user_id:
                user = session.exec(select(User).where(User.id == UUID(user_id))).first()
                if user:
                    return  # Valid JWT

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Try API token (gw_xxx format)
    if _is_api_token(token):
        # Narrow candidates by stored prefix so we only run the expensive
        # bcrypt check against tokens that can actually match.
        api_tokens = session.exec(
            select(APIToken).where(
                APIToken.revoked_at.is_(None),
                APIToken.token_prefix == get_token_prefix(token),
            )
        ).all()

        for api_token in api_tokens:
            if verify_api_token(token, api_token.token_hash):
                # Update last_used_at
                api_token.last_used_at = datetime.utcnow()
                session.add(api_token)
                session.commit()
                return  # Valid API token

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Legacy: Check against API_KEY env var (deprecated)
    if settings.api_key:
        if token == settings.api_key:
            if has_users:
                logger.warning(
                    "Using deprecated API_KEY authentication. "
                    "Consider migrating to user accounts with API tokens. "
                    "See README for migration instructions."
                )
            return  # Valid legacy API key

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    session: Session = Depends(get_session),
):
    """
    Get the currently authenticated user.

    For JWT tokens, returns the associated user.
    For API tokens, returns the user who owns the token.
    For legacy API_KEY, returns None (no user context).
    """
    from app.core.auth import decode_access_token, get_token_prefix, verify_api_token
    from app.core.config import get_settings
    from app.models.api_token import APIToken
    from app.models.user import User

    settings = get_settings()
    token = _get_token_from_request(request, credentials)

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # JWT token
    if _is_jwt_token(token):
        payload = decode_access_token(token)
        if payload:
            user_id = payload.get("sub")
            if user_id:
                user = session.exec(select(User).where(User.id == UUID(user_id))).first()
                if user:
                    return user

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # API token
    if _is_api_token(token):
        api_tokens = session.exec(
            select(APIToken).where(
                APIToken.revoked_at.is_(None),
                APIToken.token_prefix == get_token_prefix(token),
            )
        ).all()

        for api_token in api_tokens:
            if verify_api_token(token, api_token.token_hash):
                # Update last_used_at
                api_token.last_used_at = datetime.utcnow()
                session.add(api_token)
                session.commit()

                # Get the user
                user = session.exec(
                    select(User).where(User.id == api_token.user_id)
                ).first()
                if user:
                    return user

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Legacy API_KEY - no user context
    if settings.api_key and token == settings.api_key:
        # Check if any users exist
        user = session.exec(select(User)).first()
        if user:
            # Return the first (admin) user for legacy compatibility
            return user
        # No users exist, can't return a user
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account required for this endpoint. Please set up an admin account.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
