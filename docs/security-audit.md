# Ghostwriter Security Audit

**Scope:** Ghostwriter backend and web frontend as deployed to the public internet, including reverse-proxy deployments.

**Method:** Static review of backend and frontend code paths that handle authentication, API tokens, downloads, OAuth, configuration, and outbound fetching. No dynamic testing or dependency CVE scanning performed.

## Executive Summary

The Ghostwriter service is functional but unsafe for direct internet exposure in its current configuration. The most critical risks are first-run takeover due to unauthenticated setup mode, OAuth flow vulnerabilities (missing state/PKCE), and token leakage via query parameters. Additional high risks include SSRF through unvalidated feed/article URLs and permissive CORS with credentials. These issues are fixable with straightforward changes in auth bootstrapping, OAuth hardening, token transport, and outbound request validation.

## Findings

### Critical

1. **First-run takeover via unauthenticated setup mode**
   - **Impact:** Any attacker can create the first admin if the service is exposed before initialization.
   - **Evidence:** Auth is disabled if no users exist and `API_KEY` is unset. `/auth/register` is public.
   - **Affected files:** `ghostwriter/app/core/security.py`, `ghostwriter/app/api/auth.py`.
   - **Recommendation:** Require a bootstrap secret or allowlist localhost-only registration. Disable “auth disabled” mode when running on public interfaces.

2. **OAuth flow is missing `state` and PKCE (OAuth CSRF / account binding)**
   - **Impact:** Attacker can bind their Gmail account to a victim’s instance or hijack OAuth flows.
   - **Evidence:** `/newsletters/oauth/start` is unauthenticated and callback does not validate state.
   - **Affected files:** `ghostwriter/app/api/newsletters.py`, `ghostwriter/app/services/newsletter_service.py`.
   - **Recommendation:** Add `state` and PKCE; store state server-side and verify on callback. Require authentication to initiate OAuth.

3. **API tokens in query parameters for downloads**
   - **Impact:** Tokens leak via logs, referrers, browser history, proxies, and shared links.
   - **Evidence:** Frontend builds download URLs with `?api_key=`; backend accepts tokens in query params.
   - **Affected files:** `ghostwriter/frontend/src/lib/api/client.ts`, `ghostwriter/app/core/security.py`.
   - **Recommendation:** Use `Authorization` header with fetch+blob or short-lived signed URLs.

### High

4. **SSRF via feed and article fetching**
   - **Impact:** An attacker can access internal services or metadata (e.g., `169.254.169.254`).
   - **Evidence:** Feed URLs and article URLs are fetched without scheme/IP allowlist validation.
   - **Affected files:** `ghostwriter/app/services/content_processor.py`, `ghostwriter/app/api/feeds.py`.
   - **Recommendation:** Enforce `http/https`, block private/link-local IPs, resolve DNS and re-check, optionally proxy outbound requests.

5. **Permissive CORS with credentials**
   - **Impact:** Cross-origin abuse if tokens leak or browsers attach credentials.
   - **Evidence:** `allow_origins=["*"]` and `allow_credentials=True`.
   - **Affected files:** `ghostwriter/app/main.py`.
   - **Recommendation:** Restrict origins to the public UI hostname(s); disable credentials if not required.

### Medium

6. **Untrusted `X-Forwarded-*` headers**
   - **Impact:** Host/scheme spoofing could affect OAuth callbacks and absolute URL generation behind proxies.
   - **Evidence:** Proxy headers are accepted from any client without trust enforcement.
   - **Affected files:** `ghostwriter/app/main.py`.
   - **Recommendation:** Only trust forwarded headers from known proxy IPs or configure Uvicorn’s trusted proxy settings.

7. **Wallabag client secret returned to frontend**
   - **Impact:** Secret exposure to any authenticated UI user, and possible exfiltration via XSS.
   - **Evidence:** `client_secret` is returned in `/config/wallabag` response; stored plaintext in DB.
   - **Affected files:** `ghostwriter/app/api/config.py`, `ghostwriter/app/models/wallabag_config.py`.
   - **Recommendation:** Mask `client_secret` like `password`; avoid returning secrets to the browser; encrypt at rest if feasible.

8. **No rate limiting on auth endpoints**
   - **Impact:** Brute-force attacks against `/auth/login` and `/auth/register`.
   - **Evidence:** No rate limiting or lockout mechanism in auth routes.
   - **Affected files:** `ghostwriter/app/api/auth.py`.
   - **Recommendation:** Add per-IP rate limits and account lockout/backoff.

### Low

9. **Public API docs exposed**
   - **Impact:** Increased reconnaissance surface.
   - **Evidence:** `/docs`, `/redoc`, `/openapi.json` are enabled.
   - **Affected files:** `ghostwriter/app/main.py`.
   - **Recommendation:** Disable in production or require authentication.

10. **OAuth and Gmail tokens stored in plaintext on disk**
   - **Impact:** Token theft if the host is compromised.
   - **Evidence:** Tokens saved to `gmail_token.json` in data dir.
   - **Affected files:** `ghostwriter/app/services/newsletter_service.py`.
   - **Recommendation:** Restrict file permissions, use a secrets manager, or encrypt at rest.

## API Key Leakage Risks

- Query-string tokens (`?api_key=`) are the highest-risk vector due to logs and referer headers.
- Frontend stores tokens in `localStorage`, which is vulnerable to XSS if any HTML injection is introduced later.

## Deployment Hardening Checklist

- Require a setup token or localhost-only registration for first admin.
- Set `JWT_SECRET` and remove legacy `API_KEY` after migration.
- Lock CORS to your UI origin(s).
- Enforce TLS at the reverse proxy and reject HTTP.
- Rate-limit `/auth/*` and other sensitive endpoints.
- Replace query-string download tokens with auth headers or signed URLs.
- Add SSRF protections to all outbound fetches.
- Add OAuth `state` + PKCE and require auth for OAuth initiation.
- Disable `/docs` and `/redoc` in production.

## Notes and Assumptions

- This review is static; it does not include dependency CVEs or runtime checks.
- Findings assume the instance is publicly reachable and not isolated to a trusted LAN.
