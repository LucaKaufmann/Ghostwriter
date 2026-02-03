"""Newsletter (Gmail) integration endpoints."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

from app.core.config import Settings, get_settings
from app.core.security import verify_api_key
from app.services.newsletter_service import NewsletterService
from app.api.config import PreviewArticle, PreviewResponse

router = APIRouter()
logger = logging.getLogger(__name__)


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
    state: str


# Simple HTML templates for OAuth flow
# Note: CSS curly braces are doubled to escape them from .format()
SUCCESS_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Gmail Connected</title>
    <style>
        body {{ font-family: system-ui, sans-serif; max-width: 500px; margin: 100px auto; text-align: center; }}
        .success {{ color: #059669; font-size: 48px; }}
        h1 {{ color: #111; }}
        p {{ color: #666; }}
    </style>
</head>
<body>
    <div class="success">&#10003;</div>
    <h1>Gmail Connected</h1>
    <p>Newsletter integration is now configured. You can close this window.</p>
    <p>Emails labeled <strong>{label}</strong> will be included in your digests.</p>
</body>
</html>
"""

ERROR_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Connection Failed</title>
    <style>
        body {{ font-family: system-ui, sans-serif; max-width: 500px; margin: 100px auto; text-align: center; }}
        .error {{ color: #dc2626; font-size: 48px; }}
        h1 {{ color: #111; }}
        p {{ color: #666; }}
        .detail {{ background: #fee2e2; padding: 12px; border-radius: 6px; margin-top: 20px; }}
    </style>
</head>
<body>
    <div class="error">&#10007;</div>
    <h1>Connection Failed</h1>
    <p>Could not connect to Gmail.</p>
    <div class="detail">{error}</div>
</body>
</html>
"""


@router.get("/status", response_model=NewsletterStatusResponse)
async def newsletter_status(
    settings: Settings = Depends(get_settings),
    _: None = Depends(verify_api_key),
) -> NewsletterStatusResponse:
    """Get newsletter integration status."""
    service = NewsletterService(settings)
    logger.info(f"Newsletter status check: configured={service.is_configured}, oauth_ready={service.is_oauth_ready}")
    return NewsletterStatusResponse(
        configured=service.is_configured,
        oauth_ready=service.is_oauth_ready,
        label=settings.gmail_label,
    )


@router.get("/oauth/start")
async def oauth_start(
    request: Request,
    settings: Settings = Depends(get_settings),
    _: None = Depends(verify_api_key),
) -> RedirectResponse:
    """
    Start OAuth flow - redirects to Google consent screen.

    Open this URL in a browser to authorize Gmail access.
    No API key required (user must be present to authorize).
    """
    service = NewsletterService(settings)
    if not settings.gmail_client_id or not settings.gmail_client_secret:
        logger.warning("OAuth start failed: Gmail client ID and secret not configured")
        return HTMLResponse(
            content=ERROR_HTML.format(error="Gmail client ID and secret not configured"),
            status_code=400,
        )

    # Build callback URL from current request
    callback_url = str(request.url_for("oauth_web_callback"))
    auth_url = service.get_auth_url(callback_url)
    logger.info(f"OAuth flow started, callback URL: {callback_url}")
    return RedirectResponse(url=auth_url)


@router.get("/oauth/callback", name="oauth_web_callback")
async def oauth_web_callback(
    code: str = Query(None),
    error: str = Query(None),
    state: str = Query(None),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    """
    OAuth callback - receives redirect from Google after user authorizes.

    This endpoint is called by Google, not by the user directly.
    """
    if error:
        logger.error(f"OAuth callback received error from Google: {error}")
        return HTMLResponse(
            content=ERROR_HTML.format(error=f"Google returned error: {error}"),
            status_code=400,
        )

    if not code:
        logger.error("OAuth callback received no authorization code")
        return HTMLResponse(
            content=ERROR_HTML.format(error="No authorization code received"),
            status_code=400,
        )

    service = NewsletterService(settings)

    try:
        await service.exchange_code_with_callback(code, state)
    except Exception as e:
        logger.error(f"OAuth token exchange failed: {e}")
        return HTMLResponse(
            content=ERROR_HTML.format(error=str(e)),
            status_code=400,
        )

    logger.info(f"OAuth flow completed successfully, label: {settings.gmail_label}")
    return HTMLResponse(
        content=SUCCESS_HTML.format(label=settings.gmail_label),
        status_code=200,
    )


@router.post("/oauth/init", response_model=OAuthInitResponse)
async def oauth_init(
    redirect_uri: str = Query(..., description="OAuth redirect URI"),
    settings: Settings = Depends(get_settings),
    _: None = Depends(verify_api_key),
) -> OAuthInitResponse:
    """Get Google OAuth consent URL (for manual flow)."""
    service = NewsletterService(settings)
    if not settings.gmail_client_id or not settings.gmail_client_secret:
        logger.warning("OAuth init failed: Gmail client ID and secret not configured")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Gmail client ID and secret must be configured",
        )
    auth_url = service.get_auth_url(redirect_uri)
    logger.info(f"OAuth init: generated auth URL for redirect_uri={redirect_uri}")
    return OAuthInitResponse(auth_url=auth_url)


@router.post("/oauth/callback")
async def oauth_callback_post(
    body: OAuthCallbackRequest,
    settings: Settings = Depends(get_settings),
    _: None = Depends(verify_api_key),
) -> dict:
    """Exchange OAuth authorization code for tokens (for manual flow)."""
    service = NewsletterService(settings)
    try:
        await service.exchange_code_with_callback(body.code, body.state)
    except Exception as e:
        logger.error(f"OAuth token exchange (POST) failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OAuth token exchange failed: {e}",
        )
    logger.info("OAuth token exchange (POST) completed successfully")
    return {"status": "ok", "message": "Gmail token saved successfully"}


@router.post("/preview", response_model=PreviewResponse)
async def preview_newsletters(
    settings: Settings = Depends(get_settings),
    _: None = Depends(verify_api_key),
) -> PreviewResponse:
    """Preview newsletter articles without marking them as read."""
    service = NewsletterService(settings)
    if not service.is_configured:
        logger.warning("Newsletter preview requested but integration is not configured")
        return PreviewResponse(status="error", detail="Newsletter integration is not configured")

    try:
        logger.info("Fetching newsletter preview")
        articles = await service.fetch_newsletters()
        preview_articles = [
            PreviewArticle(
                title=a.title,
                url=a.url,
                author=a.author,
                word_count=a.word_count if a.word_count else None,
            )
            for a in articles
        ]
        logger.info(f"Newsletter preview: found {len(preview_articles)} articles")
        return PreviewResponse(status="ok", count=len(preview_articles), articles=preview_articles)
    except Exception as e:
        logger.error(f"Newsletter preview failed: {e}")
        return PreviewResponse(status="error", detail=str(e))
