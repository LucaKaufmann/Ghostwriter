# JOURNEY-01 result

Status: implementation and local checks passed; independent Sol review corrections accepted; awaiting hosted CI.

- Base: `df28f112ce14a2f1030173cbbcf05314c0f11453` (`codex/sync-server-verified-base`).
- Branch/worktree: `codex/journey-01-fixture-flow` at `/private/tmp/epilogue-backlog-20260927/journey-01`.
- Behavior: deterministic synthetic RSS and provider boundaries drive a real digest pipeline, SQLite persistence, EPUB/PDF generation, local HTML reader, episode failure/retry, MP3 file, and token-scoped private RSS. Referenced digest manual deletion returns 409; scheduled cleanup skips it. A second user cannot list/open the episode or download it with that user's feed token.
- Backend: `python -m pytest -q tests/test_reading_listening_journey.py --tb=short --show-capture=no` — 1 passed; full `python -m pytest -q --tb=short --show-capture=no` — 374 passed, 3 warnings (Python 3.11.16). The journey test has its own SQLite database and output directory.
- Frontend: `npm run check` — 0 errors, 0 warnings; `JOURNEY_PYTHON=<isolated venv python> npm run test:e2e -- --config=tests/e2e/reading-listening.playwright.config.ts` — 1 passed (Node 24.21.0, npm 11.19.0, Playwright 1.58.2, Chromium). The latter required sandbox escalation to bind loopback ports; no external network or service was used.
- Render review: worker and root inspected reader, failure, and ready screenshots at `ghostwriter/docs/fixture-journey-assets/`; layout is readable and no credentials or private feed URLs are visible. Playwright keeps the full synthetic trace under `ghostwriter/frontend/test-results/` for local inspection.
- Mocked boundaries: RSS transport (the real XML parser and Bindery selection run), extraction, cover generation, script provider, audio provider. MP3 is real silent media produced by local `ffmpeg`; real EPUB/PDF renderer and file endpoints are exercised. No real audio quality, offline/native behavior, or device scheduler is claimed.
- Production code/schema changes: none. No migration.
- Review: root inspected all screenshots. Initial independent Sol review found default Playwright discovery would run the backend-dependent spec in the Node-only browser job. Root added explicit discovery exclusion, a separately provisioned live-journey workflow, and ffmpeg in backend CI. Default test listing remains21; dedicated listing is1. Correction Sol review is clean (82a62d4); hosted execution pending. Combined server/recovery/journey/readiness candidate ec340d5 passed all401 backend tests.
