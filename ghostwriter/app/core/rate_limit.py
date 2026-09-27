"""Simple in-memory rate limiting utilities."""

from __future__ import annotations

import time
from collections import OrderedDict, deque
from dataclasses import dataclass

from fastapi import HTTPException, Request, status

from app.core.config import get_settings


@dataclass
class _Bucket:
    hits: deque[float]
    last_seen: float


class RateLimiter:
    def __init__(
        self, max_requests: int, window_seconds: int, max_clients: int = 10_000
    ) -> None:
        if max_clients < 1:
            raise ValueError("max_clients must be positive")
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.max_clients = max_clients
        self._hits: OrderedDict[str, _Bucket] = OrderedDict()

    def allow(self, key: str) -> bool:
        now = time.time()
        cutoff = now - self.window_seconds

        # Buckets are ordered by last request, so expired clients leave from
        # the front without scanning every active client on each attempt.
        while self._hits:
            oldest = next(iter(self._hits.values()))
            if oldest.last_seen >= cutoff:
                break
            self._hits.popitem(last=False)

        bucket = self._hits.get(key)
        if bucket is None:
            if len(self._hits) >= self.max_clients:
                self._hits.popitem(last=False)
            bucket = _Bucket(deque(), now)
            self._hits[key] = bucket
        else:
            bucket.last_seen = now
            self._hits.move_to_end(key)

        while bucket.hits and bucket.hits[0] < cutoff:
            bucket.hits.popleft()

        if len(bucket.hits) >= self.max_requests:
            return False

        bucket.hits.append(now)
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
