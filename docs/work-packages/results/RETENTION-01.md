# RETENTION-01 result

Status: contract and synthetic evidence ready for root review; no product deletion change.

Base: `de68d540ea67383a3843b8085659d29dcf19baaa` (`codex/env-01-hermetic-tests`), branch `codex/retention-01-deletion-contract`. Head: set by the scoped commit. PR target: `LucaKaufmann/Ghostwriter`, base `codex/env-01-hermetic-tests`.

The accepted policy blocks manual deletion and skips scheduled cleanup whenever any episode references the digest, regardless of status. The contract assigns digest-owned article, feedback, EPUB and cached PDF cleanup; preserves episode/audio, shared covers, media transcripts and historical orphan files; and defines a durable `deleting` marker, retry order, privacy guards, and queue/download/PDF coordination. It needs no schema migration. `docs/decisions/digest-retention.md` is the implementable RETENTION-02 handoff; `ghostwriter/tests/fixtures/retention_cases.json` is its synthetic acceptance set.

Current-behavior probe (temporary SQLite database and synthetic files only):

```
cd ghostwriter
/private/tmp/epilogue-wave1-20260927/env-01/ghostwriter/.venv/bin/python tests/fixtures/retention_probe.py
{"article_exists": true, "digest_exists": false, "epub_exists": false, "pdf_exists": true, "reported_deleted": 1, "unrelated_exists": true}
```

The result proves the scheduled path currently leaves source content and PDF while reporting deletion. The probe avoids importing provider code, loads no worktree `.env`, and touches only a temporary directory.

Verification on Python 3.11 in the read-only ENV-01 virtual environment:

- `python -m pytest -q tests/test_digest_download_formats.py tests/test_podcast_api.py`: 94 passed, 2 dependency warnings.
- `python -m json.tool tests/fixtures/retention_cases.json`: passed.
- `python -m compileall -q tests/fixtures/retention_probe.py`: passed.
- `ruff check tests/fixtures/retention_probe.py`: passed.
- `git diff --cached --check`: passed.

Review: checked the scheduled/manual order, article/feedback/media/schedule references, one-off privacy path, episode creation, PDF generation, and filename download. No runtime fix is claimed. RETENTION-02 must coordinate the narrow episode queue transaction seam, including multi-digest creation, and lazy `FileResponse` open behavior; current tests do not prove the future concurrency contract. No merge, deployment, real provider, or production-content operation was performed.
