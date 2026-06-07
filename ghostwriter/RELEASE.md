# Ghostwriter Releases

Ghostwriter stable releases are published as Docker images to `ghcr.io/lucakaufmann/ghostwriter`.

## Release Checklist

1. Start from a clean branch based on current `main`.
2. Bump `ghostwriter/app/__init__.py` and `ghostwriter/pyproject.toml` to the release version.
3. Update this file with release notes and any operational migration notes.
4. Activate the backend virtualenv or put it on `PATH`:
   ```bash
   source venv/bin/activate
   ```
   If the venv is not activated, prefix backend commands with
   `PATH="$PWD/venv/bin:$PATH"` so tests that shell out to `alembic` use the
   project executable.
5. Run backend checks:
   ```bash
   python -m pytest -q \
     tests/test_health.py \
     tests/test_feeds.py \
     tests/test_auth_registration.py \
     tests/test_alembic_bootstrap.py \
     tests/test_podcast_multi_digest_migration.py \
     tests/test_digest_download_formats.py \
     tests/test_article_eligibility_filter.py \
     tests/test_markdown_utils.py \
     --durations=10
   ```
6. Run targeted tests for the changed release surface.
7. Verify Alembic head and migration paths:
   ```bash
   alembic heads
   DATA_DIR="$(mktemp -d)" alembic upgrade head
   ```
8. Run frontend checks with Node 24, matching CI:
   ```bash
   cd frontend
   npm ci
   npm run check
   npm run build
   ```
9. Build and smoke-test the container locally with `VERSION=<release>`.
10. Merge the release prep PR into `main`.
11. Tag the merge commit:
    ```bash
    git tag -a ghostwriter-vX.Y.Z -m "Ghostwriter X.Y.Z"
    git push origin ghostwriter-vX.Y.Z
    ```
12. Wait for the `Ghostwriter Image` workflow to publish the multi-arch image.
13. Verify GHCR package visibility and direct image pull before Compose:
    ```bash
    docker manifest inspect ghcr.io/lucakaufmann/ghostwriter:X.Y.Z
    docker pull ghcr.io/lucakaufmann/ghostwriter:X.Y.Z
    ```
    If an unauthenticated public pull is expected, these commands must work
    without a registry login. If authenticated pulls are intended, document the
    required `docker login ghcr.io` step in the release notes.
14. Create a deployment `.env` from `.env.example` before Compose verification;
    the service uses `env_file: .env`, so `docker compose pull` fails before
    contacting GHCR when `.env` is missing.
15. Verify a pinned Compose pull, `/api/health`, startup logs, login, settings,
    digest listing, and podcast feed endpoints.

The frontend package is private app build metadata and is not used for Docker release versioning; leave `ghostwriter/frontend/package.json` unchanged unless the frontend starts publishing its own package artifact.

## 1.1.0 - 2026-06-07

### Highlights

- Added podcast digest generation with AI-powered text-to-speech.
- Added one-off podcast creation flows for ad hoc source material.
- Added flexible podcast schedules, multiple recurring schedules, host controls, feed base URL support, and stable episode numbering.
- Added PDF digest generation and download controls alongside EPUB output.
- Added AI-generated digest covers, deterministic cover overlays, and cover settings.
- Added KOReader plugin support with configured plugin download.
- Added media transcript processing, retry handling, web reader improvements, and richer digest article formatting.
- Added Wallabag, newsletter, and media-processing improvements across sync and digest generation.
- Added the Svelte web UI refresh for dashboard, feeds, digests, reader, newsletters, settings, navigation, theme support, accessibility, and smoke coverage.

### Fixes

- Stabilized podcast feed episode numbers across feed regeneration.
- Prevented broken podcast episodes after ElevenLabs quota exhaustion.
- Honored podcast scheduler enablement without legacy fallback behavior.
- Filtered promotional digest articles.
- Hardened Gmail OAuth token refresh failures.
- Fixed embedded EPUB cover metadata and gpt-image-1 cover request compatibility.
- Fixed newsletter parsing, mobile responsiveness, Wallabag/newsletter synthetic feed IDs, and sync performance issues.

### Operations

- Published Ghostwriter images to GitHub Container Registry.
- Added PR checks for backend smoke tests and frontend check/build.
- Simplified first-run `.env` and quick-start documentation.
- Consolidated database changes onto Alembic; release `1.1.0` upgrades to Alembic head `021`.
- Container startup continues to run `alembic upgrade head` before starting Uvicorn.

### Migration Notes

- Existing deployments should back up the Ghostwriter data volume before upgrading.
- Upgrade with the published image:
  ```bash
  GHOSTWRITER_VERSION=1.1.0 docker compose pull
  GHOSTWRITER_VERSION=1.1.0 docker compose up -d
  ```
- Verify `/api/health` reports `version: "1.1.0"` and container logs show migrations completed.
- Roll back by pinning `GHOSTWRITER_VERSION=1.0.0`; restore the pre-upgrade data backup if database behavior needs to be reverted.

### Release Process Feedback

- Public consumption was not fully verified during the 1.1.0 release because
  unauthenticated GHCR manifest inspection and `docker pull` returned
  `unauthorized` after the publish workflow succeeded. Confirm package
  visibility or authenticated-pull policy before the next release is announced.
- `docker compose pull` needs a local `.env`; otherwise Compose fails before it
  reaches GHCR. Use direct `docker pull` for registry-only verification, then
  run Compose verification with a real deployment `.env`.
- Local backend checks are smoother with an activated venv because Alembic tests
  invoke `alembic` by executable name.
- CI uses Node 24; local release verification should match that major version.
- The runtime build currently installs `yt-dlp` without a pinned version, so
  release image contents can vary over time for the same source commit.
