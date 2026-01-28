"""JWT and authentication utilities."""

import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT configuration
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7


def get_jwt_secret() -> str:
    """
    Get the JWT secret key.

    If JWT_SECRET is not set, generates a random one and logs a warning.
    Note: Random secrets won't persist across restarts, invalidating all tokens.
    """
    settings = get_settings()
    secret = getattr(settings, "jwt_secret", None) or ""

    if not secret:
        # Generate a random secret (tokens won't survive restart)
        logger.warning(
            "JWT_SECRET not set - generating random secret. "
            "Tokens will be invalidated on restart. "
            "Set JWT_SECRET environment variable for persistent sessions."
        )
        # Store in a module-level variable so it persists within this process
        global _runtime_jwt_secret
        if "_runtime_jwt_secret" not in globals() or not _runtime_jwt_secret:
            _runtime_jwt_secret = secrets.token_urlsafe(32)
        return _runtime_jwt_secret

    return secret


# Module-level storage for runtime-generated secret
_runtime_jwt_secret: Optional[str] = None


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return pwd_context.hash(password)


def create_access_token(
    user_id: UUID,
    username: str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create a JWT access token.

    Args:
        user_id: The user's UUID.
        username: The user's username.
        expires_delta: Optional custom expiration time.

    Returns:
        Encoded JWT string.
    """
    if expires_delta is None:
        expires_delta = timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)

    expire = datetime.utcnow() + expires_delta
    to_encode = {
        "sub": str(user_id),
        "username": username,
        "exp": expire,
        "iat": datetime.utcnow(),
    }
    encoded_jwt = jwt.encode(to_encode, get_jwt_secret(), algorithm=ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[dict]:
    """
    Decode and validate a JWT access token.

    Args:
        token: The JWT string.

    Returns:
        The decoded payload if valid, None otherwise.
    """
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[ALGORITHM])
        return payload
    except JWTError as e:
        logger.debug(f"JWT decode error: {e}")
        return None


def generate_api_token() -> str:
    """
    Generate a new API token.

    Format: gw_<32 random hex bytes> (67 characters total)
    """
    random_part = secrets.token_hex(32)
    return f"gw_{random_part}"


def hash_api_token(token: str) -> str:
    """Hash an API token using bcrypt."""
    return pwd_context.hash(token)


def verify_api_token(plain_token: str, hashed_token: str) -> bool:
    """Verify an API token against its hash."""
    return pwd_context.verify(plain_token, hashed_token)


def get_token_prefix(token: str) -> str:
    """
    Get the displayable prefix of a token.

    Returns the first 11 characters (e.g., "gw_abc1234...").
    """
    return token[:11] + "..."
