# INPUT-01 result

Branch `codex/input-01-sync-validation`, based on FETCH-01. Malformed or mixed digest UUID lists return422 before sync work; whitespace, empty components and duplicates remain accepted. Feed create/update/batch sync convert normalized DNS validation failures to422; every batch URL validates before activity/feed writes. No schema, DTO, one-off privacy or dirty-write policy change.

ENV-01 Python3.11.16 fixture command: `python -m pytest -q tests/test_sync_validation.py tests/test_feeds.py tests/test_podcast_api.py` —102passed. Fixtures cover no partial batch writes and successful retry after DNS recovers. Scoped Ruff and diff checks pass; broader legacy lint warnings remain outside this fix.

The initial independent Sol review found that the new renamed422 status alias did not exist on older supported Starlette. Both paths now use numeric422, which is compatible across the declared range without adding deprecation warnings. No real network, content or providers were used. Final Sol correction review is clean; the branch is rebased on accepted FETCH-01 at25d89df.
