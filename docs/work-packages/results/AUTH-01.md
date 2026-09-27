# AUTH-01 result

- Base: `e6e62677fe4f5b8f516e226a48080008cafc04e0`; branch: `codex/auth-01-auth-lifecycle`.
- Login and first-admin registration now consume the configured shared client-IP auth bucket before database work. Existing 429 response and SQLite registration lock are preserved.
- `verify_api_key` now uses FastAPI's managed `get_session` dependency. The podcast direct caller passes its existing request session explicitly.
- Added tests for shared threshold, client separation, expiration, disabled limiter, setup/JWT/API/legacy auth, token last-use/revocation, and pool checkout returning to baseline on successful, rejected, and exceptional requests.
- Verification: ENV-01 disposable Python 3.11 environment with SQLModel 0.0.31, `LITELLM_MODE=PRODUCTION`, `LITELLM_LOCAL_MODEL_COST_MAP=true`, and blank integration settings. `python -m pytest -q --tb=short tests/test_auth_registration.py tests/test_auth_security.py tests/test_auth_rate_limit.py tests/test_podcast_api.py`: 100 passed, 2 warnings. `python -m compileall -q` on changed Python paths, `ruff check` on new test files, and `git diff --check`: passed. Existing source files contain unrelated Ruff findings; no broad lint cleanup was attempted. Initial fresh SQLModel 0.0.47 run failed because it rejects the repository's existing naive datetime defaults; ENV-01 narrowed the compatible range.
- No schema or public response-model changes; no external provider calls, merge, or deployment.
