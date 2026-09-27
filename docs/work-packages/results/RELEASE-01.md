# RELEASE-01 provisional result

Worktree `/private/tmp/epilogue-backlog-20260927/release-01`, branch `codex/release-01-readiness`; preparation commits2e22a02 and900d824 on verified base df28f112. Not published or accepted as final release readiness: final sync026/recovery027 integration and restore identity command fixture remain pending.

Captured tagged1.1.0 SQLModel SQLite schema (19 tables) with seven synthetic rows. Tests run actual Alembic upgrades, application lifespan/health/reader, stopped-volume backup/restore and shell entrypoint failure control flow. Four Compose volumes are represented by synthetic byte sentinels; no media quality or production backup claim.

ENV fixture runtime Python3.11.16. `python -m pytest -q tests/test_release_recovery.py tests/test_alembic_bootstrap.py tests/test_podcast_multi_digest_migration.py`:7 passed. Optional Ollama volume addition: affected restore test1 passed. Sol full preparation review found missing023 preferences verification and incomplete socket guard; both corrected. After correction, readiness test file5 passed; scoped Ruff/diff checks passed. Sol commit review900d824 clean. Remaining warnings: Starlette/httpx deprecation.

Initial harness attempt used `python -m alembic` from source directory and hit repository-package shadowing. Corrected to invoke current environment's Alembic console executable and explicitly order subprocess site-packages before app source. No production code or historical release notes changed. No provider, registry publication, deployment or real-content calls.
