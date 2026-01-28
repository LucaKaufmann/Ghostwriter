#!/usr/bin/env python3
"""Verify Gmail newsletter integration setup."""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.config import get_settings


def main() -> None:
    settings = get_settings()
    token_path = os.path.join(settings.data_dir, "gmail_token.json")

    print("=== Gmail Newsletter Setup Verification ===\n")

    # Check client credentials
    if settings.gmail_client_id:
        print(f"✓ Gmail Client ID: configured ({settings.gmail_client_id[:20]}...)")
    else:
        print("✗ Gmail Client ID: not set (GMAIL_CLIENT_ID)")

    if settings.gmail_client_secret:
        print("✓ Gmail Client Secret: configured")
    else:
        print("✗ Gmail Client Secret: not set (GMAIL_CLIENT_SECRET)")

    print(f"  Gmail Label: {settings.gmail_label}")
    print(f"  Max Articles: {settings.gmail_max_articles}")

    # Check token
    print()
    if os.path.exists(token_path):
        try:
            with open(token_path) as f:
                token_data = json.load(f)
            has_refresh = "refresh_token" in token_data
            print(f"✓ Token file exists: {token_path}")
            print(f"  Has refresh token: {'yes' if has_refresh else 'no'}")
        except Exception as e:
            print(f"✗ Token file exists but is invalid: {e}")
    else:
        print(f"✗ Token file not found: {token_path}")
        if settings.gmail_client_id and settings.gmail_client_secret:
            print("  → Use POST /newsletters/oauth/init to start OAuth flow")

    # Summary
    print()
    has_creds = bool(settings.gmail_client_id and settings.gmail_client_secret)
    has_token = os.path.exists(token_path)

    if has_creds and has_token:
        print("Status: CONFIGURED - Newsletter integration is ready")
    elif has_creds:
        print("Status: OAUTH READY - Complete OAuth flow to finish setup")
    else:
        print("Status: NOT CONFIGURED - Set GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET")


if __name__ == "__main__":
    main()
