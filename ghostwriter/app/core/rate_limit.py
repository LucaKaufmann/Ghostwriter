"""Simple in-memory rate limiting utilities."""

from __future__ import annotations

import time
from collections import deque
from typing import Deque

from fastapi import HTTPException, Request, status

from app.core.config import get_settings


class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, Deque[float]] = {}

    def allow(self, key: str) -> bool:
        now = time.time()
        bucket = self._hits.setdefault(key, deque())

        # Drop old entries
        cutoff = now - self.window_seconds
        while bucket and bucket[0] < cutoff:
            bucket.popleft()

        if len(bucket) >= self.max_requests:
            return False

        bucket.append(now)
        return True


_auth_limiter = RateLimiter(max_requests=10, window_seconds=60)


def check_auth_rate_limit(request: Request) -> None:
    """Rate limit auth endpoints per client IP."""
    settings = get_settings()
    if not settings.auth_rate_limit_enabled:
        return

    client_ip = getattr(request.client, "host", "unknown")
    key = f"auth:{client_ip}"

    # Update limiter configuration if settings changed
    _auth_limiter.max_requests = settings.auth_rate_limit_max
    _auth_limiter.window_seconds = settings.auth_rate_limit_window_seconds

    if not _auth_limiter.allow(key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many authentication attempts. Please try again later.",
        )
