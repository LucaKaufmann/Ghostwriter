# INGEST-01 result

- Base: `de68d540ea67383a3843b8085659d29dcf19baaa` (ENV-01 integrated branch).
- Verified implementation commit: `ee895d90504718f927bc5305e4c38ac57ee8eec2`.
- Branch: `codex/ingest-01-source-editions`; intended PR base: `codex/env-01-hermetic-tests` (PR #75 dependency).
- Scope: `ghostwriter/app/worker/bindery.py` and `ghostwriter/tests/test_bindery_source_combinations.py`.

The pipeline now checks all enabled sources before completing an empty digest. Wallabag-only, Gmail-only, podcast-only, and YouTube-only editions produce article rows and a readable, nonempty EPUB. Empty active RSS feeds no longer hide completed media. The existing completed, zero-article status and API shape remain for truly empty input. Wallabag summarization follows the service's effective DB or environment mode.

Offline tests cover disabled inclusion/configuration, seen and filtered items, consumed transcripts, both directions of DB mode override, environment fallback, raw content on an LLM error, and a failure before EPUB output followed by one successful retry. The failure test checks that no article or seen rows, media consumption, or remote processed markers occur before output.

Verification from `ghostwriter/` using the ENV-01 disposable venv (Python 3.11.16; Ruff 0.16.9):

```text
python -m pytest -q tests/test_bindery_source_combinations.py tests/test_bindery_seen_articles.py tests/test_bindery_filtering.py tests/test_digest_ordering_and_epub.py tests/test_bindery_digest_filenames.py tests/test_newsletter_service.py
35 passed, 2 upstream dependency warnings

python -m ruff check app/worker/bindery.py tests/test_bindery_source_combinations.py
All checks passed!

git diff --check
Passed
```

No live Wallabag, Gmail, podcast, YouTube, or LLM provider call was made. Later failure boundaries remain separate: EPUB creation, article persistence, media consumption, remote acknowledgement, and final completion are not one transaction. RECOVERY-01 will examine those boundaries; this PR claims only the pre-output retry boundary. No schema or public API change, merge, or deployment.

Next action: root inspection and independent Sol review; after acceptance, publish the focused PR.
