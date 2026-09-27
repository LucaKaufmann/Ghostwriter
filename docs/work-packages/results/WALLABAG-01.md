# WALLABAG-01 result

Base: INGEST-01 `679bd909d5780e55be21d8ea5347e3ea6a9a54d3` (PR77 atop ENV75).
Branch: `codex/wallabag-01-token-isolation`.

OAuth tokens are cached per service, whose effective DB/env configuration is an immutable snapshot. A newly constructed service authenticates independently; it cannot inherit another origin/account/client's token. Existing services finish against their original configuration. Valid tokens are reused within a service until the existing 60-second refresh margin. Failed refresh raises without sending an expired token to the API, and later retry can recover. The DB factory now uses the same constructor. OAuth failure response bodies are no longer logged.

This intentionally trades cross-instance token reuse for a small, bounded cache with no shared secret key or invalidation lifecycle. No API, schema, mode, tagging or source-selection behavior changes. HTTP transport redirect behavior is unchanged and not a new security guarantee.

Verification from `ghostwriter/` using the read-only ENV-01 Python3.11.16 virtualenv:

`python -m pytest -q tests/test_wallabag_service.py tests/test_newsletter_service.py tests/test_bindery_source_combinations.py tests/test_bindery_seen_articles.py tests/test_bindery_digest_filenames.py tests/test_bindery_filtering.py`

Passed: **32 tests**, including 9 new OAuth/API fixtures for all five credential/destination fields, mutable input settings, concurrent configurations, expiry/failure/retry, and persisted DB changes plus env fallback. The existing Starlette/httpx and Pydantic ReadOnly warnings remain. No external account or provider calls.

Changed-file Ruff and `git diff --check` passed. Independent Sol review and hosted checks pending at this checkpoint.
