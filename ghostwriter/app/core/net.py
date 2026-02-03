"""Network safety utilities for outbound requests."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from app.core.config import Settings, get_settings


def _is_private_ip(ip_str: str) -> bool:
    ip = ipaddress.ip_address(ip_str)
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
    )


def _resolve_host(hostname: str) -> list[str]:
    results = []
    for family, _, _, _, sockaddr in socket.getaddrinfo(hostname, None):
        if family == socket.AF_INET:
            results.append(sockaddr[0])
        elif family == socket.AF_INET6:
            results.append(sockaddr[0])
    return list(set(results))


def validate_public_url(url: str, settings: Settings | None = None) -> None:
    """
    Validate a URL for safe outbound fetching.

    Enforces:
    - http/https schemes only
    - no username/password in URL
    - no private/loopback/link-local/reserved IPs (unless allow_private_hosts is enabled)
    """
    settings = settings or get_settings()
    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        raise ValueError("Only http/https URLs are allowed")

    if parsed.username or parsed.password:
        raise ValueError("Userinfo is not allowed in URLs")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL must include a hostname")

    if settings.allow_private_hosts:
        return

    # Block obvious local hostnames
    lowered = hostname.lower()
    if lowered in ("localhost", "localhost.localdomain"):
        raise ValueError("Localhost is not allowed")

    # If hostname is an IP literal, validate directly
    try:
        if _is_private_ip(hostname):
            raise ValueError("Private or local IPs are not allowed")
        return
    except ValueError:
        # Not an IP literal; resolve DNS
        pass

    ips = _resolve_host(hostname)
    if not ips:
        raise ValueError("Hostname could not be resolved")

    for ip in ips:
        if _is_private_ip(ip):
            raise ValueError("Private or local IPs are not allowed")
