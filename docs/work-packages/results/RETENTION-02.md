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
