# WEB-02 result

Base: `67acec4e0f3607a7c0eedd318c84fd022e55a803` (`codex/web-01-browser-checks`). Branch: `codex/web-02-session-recovery`. Commit: see branch head.

Authenticated API request, upload, and download failures now use one status-aware error path. A 401 expires only the currently authenticated matching token. The layout clears TanStack Query's cache, canceling active queries and pollers, and presents the existing sign-in screen. The user can log in again and fetch fresh data. Concurrent or delayed 401 responses from an old token cannot end that new session. 403 retains credentials; 401 and 403 queries are not retried. Server and network errors keep credentials and use the existing bounded query retry policy. Public login/register failures stay local. `ApiError.isUnauthorized` now means 401 only.

Verification (Node v24.21.0, npm 11.19.0, Playwright 1.58.2):

- `npm ci` — passed, exact lockfile; no lockfile change.
- `npm run check` — passed, 0 errors/warnings (rerun after final code edit).
- `npm run build` — passed; Playwright also built the final code for its preview server.
- `npx playwright test --project=behavior` — 14 passed before adding the final network-bound test.
- `npx playwright test tests/e2e/session-expiry.spec.ts --project=behavior` — 6 passed on final code, including counted 401 (1 request), 403 (1 request), 503 (3 requests to recover), network failure (4 total attempts), delayed old-token response, re-login, and denied download.
- `git diff --check` — passed.

Browser tests used synthetic fixture responses and local Chromium. The first sandboxed Playwright invocation could not bind loopback (`EPERM`); the approved local loopback run passed. No production session or backend was used. The session UI reuses the existing login screen, so no visual baseline changed. Independent orchestrator review is pending before publication. No schema or API contract change.
