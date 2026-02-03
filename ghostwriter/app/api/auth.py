"""Authentication API endpoints."""

import logging
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlmodel import Session, select

from app.core.auth import (
    create_access_token,
    generate_api_token,
    get_token_prefix,
    hash_api_token,
    hash_password,
    verify_api_token,
    verify_password,
)
from app.core.database import get_session
from app.core.rate_limit import check_auth_rate_limit
from app.core.security import get_current_user
from app.models.api_token import (
    APIToken,
    APITokenCreate,
    APITokenCreateResponse,
    APITokenResponse,
)
from app.models.user import (
    LoginRequest,
    LoginResponse,
    User,
    UserCreate,
    UserResponse,
    UserUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ============ Public Endpoints (No Auth Required) ============


class AuthStatus:
    """Response model for auth status."""

    def __init__(self, setup_complete: bool, user_count: int):
        self.setup_complete = setup_complete
        self.user_count = user_count


@router.get("/status")
async def get_auth_status(session: Session = Depends(get_session)) -> dict:
    """
    Check if authentication setup is complete.

    Returns whether any users exist (setup complete) or if registration is needed.
    This endpoint does not require authentication.
    """
    user_count = session.exec(select(User)).first() is not None
    return {
        "setup_complete": user_count,
        "registration_open": not user_count,
    }


@router.post("/register", response_model=LoginResponse)
async def register(
    data: UserCreate,
    request: Request,
    session: Session = Depends(get_session),
) -> LoginResponse:
    """
    Register the first admin user.

    This endpoint only works when no users exist. The first user is automatically
    granted admin privileges.

    Returns a JWT token on successful registration.
    """
    # Check if any users exist
    existing_user = session.exec(select(User)).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registration is closed. An admin user already exists.",
        )

    # Check if username is taken (shouldn't be possible, but be safe)
    username_taken = session.exec(
        select(User).where(User.username == data.username)
    ).first()
    if username_taken:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already exists.",
        )

    # Create the admin user
    user = User(
        username=data.username,
        email=data.email,
        password_hash=hash_password(data.password),
        is_admin=True,  # First user is always admin
        last_login_at=datetime.utcnow(),
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    logger.info(f"First admin user created: {user.username}")

    # Generate JWT
    access_token = create_access_token(user.id, user.username)

    return LoginResponse(
        access_token=access_token,
        user=UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            is_admin=user.is_admin,
            created_at=user.created_at,
            last_login_at=user.last_login_at,
        ),
    )


@router.post("/login", response_model=LoginResponse)
async def login(
    data: LoginRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> LoginResponse:
    """
    Log in with username and password.

    Returns a JWT token on successful authentication.
    """
    # Find user
    user = session.exec(select(User).where(User.username == data.username)).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )

    # Verify password
    if not verify_password(data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )

    # Update last login
    user.last_login_at = datetime.utcnow()
    session.add(user)
    session.commit()
    session.refresh(user)

    # Generate JWT
    access_token = create_access_token(user.id, user.username)

    logger.info(f"User logged in: {user.username}")

    return LoginResponse(
        access_token=access_token,
        user=UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            is_admin=user.is_admin,
            created_at=user.created_at,
            last_login_at=user.last_login_at,
        ),
    )


@router.post("/logout")
async def logout() -> dict:
    """
    Log out (client-side only).

    JWT tokens are stateless - the client should discard the token.
    This endpoint exists for API completeness and future session invalidation.
    """
    return {"status": "ok", "message": "Logged out successfully."}


# ============ Protected Endpoints (Auth Required) ============


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserResponse:
    """Get the current authenticated user's information."""
    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        is_admin=current_user.is_admin,
        created_at=current_user.created_at,
        last_login_at=current_user.last_login_at,
    )


@router.put("/me", response_model=UserResponse)
async def update_current_user(
    data: UserUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Session = Depends(get_session),
) -> UserResponse:
    """Update the current user's information."""
    if data.email is not None:
        current_user.email = data.email

    if data.password is not None:
        current_user.password_hash = hash_password(data.password)
        logger.info(f"User changed password: {current_user.username}")

    session.add(current_user)
    session.commit()
    session.refresh(current_user)

    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        is_admin=current_user.is_admin,
        created_at=current_user.created_at,
        last_login_at=current_user.last_login_at,
    )


# ============ API Token Management ============


@router.get("/tokens", response_model=list[APITokenResponse])
async def list_api_tokens(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Session = Depends(get_session),
) -> list[APITokenResponse]:
    """List all API tokens for the current user."""
    tokens = session.exec(
        select(APIToken)
        .where(APIToken.user_id == current_user.id)
        .where(APIToken.revoked_at.is_(None))
        .order_by(APIToken.created_at.desc())
    ).all()

    return [
        APITokenResponse(
            id=token.id,
            name=token.name,
            token_prefix=token.token_prefix,
            created_at=token.created_at,
            last_used_at=token.last_used_at,
            revoked_at=token.revoked_at,
        )
        for token in tokens
    ]


@router.post("/tokens", response_model=APITokenCreateResponse)
async def create_api_token(
    data: APITokenCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Session = Depends(get_session),
) -> APITokenCreateResponse:
    """
    Create a new API token.

    WARNING: The full token is only returned in this response.
    It cannot be retrieved again - store it securely!
    """
    # Generate token
    raw_token = generate_api_token()
    token_hash = hash_api_token(raw_token)
    token_prefix = get_token_prefix(raw_token)

    # Create token record
    api_token = APIToken(
        user_id=current_user.id,
        name=data.name,
        token_hash=token_hash,
        token_prefix=token_prefix,
    )
    session.add(api_token)
    session.commit()
    session.refresh(api_token)

    logger.info(f"API token created for user {current_user.username}: {token_prefix}")

    return APITokenCreateResponse(
        id=api_token.id,
        name=api_token.name,
        token=raw_token,  # Only time the full token is returned!
        token_prefix=token_prefix,
        created_at=api_token.created_at,
    )


@router.delete("/tokens/{token_id}")
async def revoke_api_token(
    token_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Session = Depends(get_session),
) -> dict:
    """Revoke an API token."""
    token = session.exec(
        select(APIToken)
        .where(APIToken.id == token_id)
        .where(APIToken.user_id == current_user.id)
    ).first()

    if not token:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Token not found.",
        )

    if token.revoked_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token already revoked.",
        )

    token.revoked_at = datetime.utcnow()
    session.add(token)
    session.commit()

    logger.info(f"API token revoked for user {current_user.username}: {token.token_prefix}")

    return {"status": "ok", "message": "Token revoked successfully."}
    check_auth_rate_limit(request)
    check_auth_rate_limit(request)
