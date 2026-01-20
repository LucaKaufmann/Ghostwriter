"""Authentication and security utilities."""

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings, get_settings

security = HTTPBearer(auto_error=False)


async def verify_api_key(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    settings: Settings = Depends(get_settings),
) -> None:
    """
    Verify the API key from the Authorization header.

    If API_KEY is not set, authentication is disabled (LAN-only mode).

    Args:
        request: The incoming request.
        credentials: Bearer token credentials.
        settings: Application settings.

    Raises:
        HTTPException: If authentication fails.
    """
    # If no API key configured, skip authentication
    if not settings.api_key:
        return

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if credentials.credentials != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
