# RETENTION-02 result

Status: implementation committed for root's independent data-integrity review. Worktree `/private/tmp/epilogue-backlog-20260927/retention-02`, branch `codex/retention-02-safe-deletion`, base `7ceada001571a6ad8b7509fb42c03f98c60dd447`; head is the commit containing this file. No schema or Alembic revision.

Manual deletion and scheduled age cleanup now use one crash-retryable operation. It reserves the SQLite writer slot to check episode digest/article references and file ownership, persists `deleting`, unlinks only exact EPUB/PDF paths, and removes feedback/articles/parent while clearing media and schedule pointers in a final transaction. Missing files are harmless; conflicts and I/O/DB failures never count as success. A failed digest with an empty filename is deletable by ID without touching unknown files. Repeated requests after successful deletion return 404.

Content reads hide marked rows. Filename downloads require exactly one digest row and inherit ID access checks. EPUB/PDF handles open before returning a streaming response; PDF rendering uses a temporary file and a writer-transaction status check for publication. Podcast queue and feedback writes recheck source status in the same SQLite writer transaction as their write; worker scheduling occurs after commit. The per-digest lock registry uses weak values.

Verification (Python 3.11.16; hermetic ENV-01 venv, no provider/network access):

- `pytest -q tests/test_digest_retention.py tests/test_digest_download_formats.py`: 25 passed.
- `pytest -q --tb=short`: 275 passed, 3 existing dependency/mock warnings in last run.
- `ruff check app/services/digest_deletion.py tests/test_digest_retention.py tests/test_digest_download_formats.py`: passed.
- `ruff check --select I app/api/digests.py app/worker/cleanup.py app/services/podcast_service.py`: passed.
- `git diff --check`: passed.

Synthetic tests cover manual/scheduled reference blocks across episode states and article-only references, private one-off retry, ownership boundaries, empty/missing files, failed/processing eligibility, permission and final-transaction failures with retry, exact-path collisions and symlinks, unknown-file 404, queue/PDF/download concurrency, feedback, and retained cover/audio/media content. No real provider generation, deployment, or multiprocess deployment smoke was run. Root's independent review and PR publication remain.

## Review follow-up: resumable downloads

Independent review caught that the first pre-opened `StreamingResponse` lost Starlette `FileResponse` byte ranges and `Content-Length`. The follow-up keeps Starlette's response metadata, range parsing, `If-Range`, and 206/416 behavior while reading all response bodies from the already-opened file descriptor. It never uses the ASGI path-send shortcut or reopens the path after deletion. Focused API tests cover ID and filename EPUB ranges (single, suffix, open-ended, multipart, invalid, and `If-Range`), PDF ranges, and full/ranged handles consumed after unlink. Verification: focused 25 passed; full backend 275 passed; changed-test Ruff and import-sort checks passed; no provider/network access.

## Review follow-up: response dependency bounds

The pre-opened response overrides Starlette 1.7 `FileResponse` body handlers; older allowed Starlette releases use a different call path and could reopen an unlinked file. Both runtime manifests now require `fastapi>=0.141.1,<1.0.0` and `starlette>=1.7.0,<1.8.0`, matching the tested venv. To upgrade Starlette, inspect its `FileResponse.__call__`/body hooks, then run the focused digest download and retention race tests and the full backend suite before widening the upper bound in both manifests together.

Validation: installed FastAPI 0.141.1, Starlette 1.7.0, and HTTPX 0.28.1 satisfy their metadata; `pip check` passed. Offline `pip install --dry-run --no-index -r requirements.txt` and the same resolver command against the dependency list extracted from `pyproject.toml` both passed without mutation. A direct offline `pip install --dry-run .` could not prepare the local package because `hatchling` is absent from the shared read-only venv; package building was not attempted. Manifest-parity plus retention/download tests: 30 passed. Full backend suite: 275 passed. No provider or network access.

Root resolved the direct package metadata with `python -m pip install --dry-run .` (temporary build backend fetched, shared environment unchanged): passed, would install ghostwriter1.1.0. Final targeted Sol dependency review returned no actionable findings after range compatibility and retention reviews.
