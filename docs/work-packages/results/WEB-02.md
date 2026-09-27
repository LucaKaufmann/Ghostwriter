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

Browser tests used synthetic fixture responses and local Chromium. The first sandboxed Playwright invocation could not bind loopback (`EPERM`); the approved local loopback run passed. No production session or backend was used. The session UI reuses the existing login screen, so no visual baseline changed. Independent Sol review is clean after the correction below. No schema or API contract change.

## Review correction

Independent review found that clearing TanStack Query does not prevent an already running mutation from completing. A pending KOReader plugin ZIP response could therefore deliver user A's embedded API token after user B signs in. The API client now increments a session revision on every `setToken` call and checks the revision before any authenticated JSON, blob, or multipart result settles. Stale results and errors remain unsettled so old mutation success/error handlers and direct download continuations cannot run. The 401 handler also checks the revision, including when a new session happens to receive the same JWT string. Public login, registration, health, and auth status requests retain their prior behavior.

All authenticated transport paths were inspected: general JSON requests, digest/log/podcast downloads, plugin ZIP creation, manual cover upload, and podcast artwork upload. The shared download method covers digest and log files as well as podcast audio. The browser regression holds a successful old-session plugin response, expires the session through another request's 401, signs in a second synthetic user, and releases the old ZIP. No download or plugin success callback occurs; the new session remains active. The regression runs with both a distinct replacement token and the same token string.

Root final full suite `npm run test:e2e` passed **21/21**, including all behavior tests and unchanged Darwin light/dark visual snapshots.

Final verification after this correction: `npm run check` passed with 0 errors/warnings; `npm run build` passed; `npx playwright test tests/e2e/session-expiry.spec.ts --project=behavior` passed 8/8; `git diff --check` passed. Browser coverage uses fixture responses and local Chromium, with no backend or real account. Sandbox loopback still required approved local access. The stale request remains pending by design until its caller is discarded; this prevents callbacks that would otherwise fire on either resolution or rejection.
