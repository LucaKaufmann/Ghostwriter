"""Newsletter (Gmail) integration endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.core.config import Settings, get_settings
from app.core.security import verify_api_key
from app.services.newsletter_service import NewsletterService

router = APIRouter()


class NewsletterStatusResponse(BaseModel):
    """Newsletter integration status."""

    configured: bool
    oauth_ready: bool
    label: str


class OAuthInitResponse(BaseModel):
    """OAuth initialization response."""

    auth_url: str


class OAuthCallbackRequest(BaseModel):
    """OAuth callback request body."""

    code: str
    redirect_uri: str


@router.get("/status", response_model=NewsletterStatusResponse)
async def newsletter_status(
    settings: Settings = Depends(get_settings),
    _: None = Depends(verify_api_key),
) -> NewsletterStatusResponse:
    """Get newsletter integration status."""
    service = NewsletterService(settings)
    return NewsletterStatusResponse(
        configured=service.is_configured,
        oauth_ready=service.is_oauth_ready,
        label=settings.gmail_label,
    )


@router.post("/oauth/init", response_model=OAuthInitResponse)
async def oauth_init(
    redirect_uri: str = Query(..., description="OAuth redirect URI"),
    settings: Settings = Depends(get_settings),
    _: None = Depends(verify_api_key),
) -> OAuthInitResponse:
    """Get Google OAuth consent URL."""
    service = NewsletterService(settings)
    if not settings.gmail_client_id or not settings.gmail_client_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Gmail client ID and secret must be configured",
        )
    auth_url = service.get_auth_url(redirect_uri)
    return OAuthInitResponse(auth_url=auth_url)


@router.post("/oauth/callback")
async def oauth_callback(
    body: OAuthCallbackRequest,
    settings: Settings = Depends(get_settings),
    _: None = Depends(verify_api_key),
) -> dict:
    """Exchange OAuth authorization code for tokens."""
    service = NewsletterService(settings)
    try:
        await service.exchange_code(body.code, body.redirect_uri)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OAuth token exchange failed: {e}",
        )
    return {"status": "ok", "message": "Gmail token saved successfully"}
