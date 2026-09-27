# Disposable release-readiness checks

Status: preparation on the integrated reliability branch, 2026-09-27. No release, image publication, production backup or deployment is authorized by this document. Final evidence must include the feed-sync and source-acknowledgement migrations after their implementation is accepted.

## Repeatable verification

Use the declared backend environment, with its `bin` directory on PATH. From `ghostwriter/`, run:

```sh
python -m pytest -q tests/test_release_recovery.py tests/test_alembic_bootstrap.py tests/test_podcast_multi_digest_migration.py
```

The readiness harness invokes that Python environment's Alembic executable, creates disposable storage and disables dotenv loading for actual application startup. App startup/health/reader requests run with IP connections, datagram sends and DNS blocked. Sources, accounts, LLM and TTS are never contacted. Existing bootstrap tests also require the activated environment and site-packages before the repository's same-named `alembic` directory on PYTHONPATH.

`tests/fixtures/release_021.sql` captures all 19 SQLModel tables from the actual `ghostwriter-v1.1.0` tag, commit `43ac1e1b7f3fd23c54c4176e6a1b4a2ca6b1f2fa`, plus seven synthetic feed/config/digest/article/seen/episode/preferences records. It was exported with SQLite `iterdump()` after creating the tagged model metadata and inserting fixed fixture values. It is not a current schema relabeled 021: the tests assert that later episode columns are absent before upgrading. No production content or credentials appear in this fixture.

Checks cover fresh migration, repeated migration and real application lifespan, 021-to-current upgrade with preserved records, a coordinated stopped-volume snapshot restored into a different directory, reader content after restart/restore, and rejection of an unknown future database revision. The entrypoint test executes its shell control flow with a substituted container mount point and stub executables to prove migration failure prevents server launch. It is separate from the real Alembic/startup tests and is not Docker validation.

Artifacts are explicitly labeled byte sentinels. Their hashes prove preservation of EPUB/PDF/audio, credential-file storage, diagnostics and optional Ollama volume content; they do not prove those formats render, audio quality, or credential validity. JOURNEY-01 owns actual generated-format and browser behavior checks. Container audio paths stay `/app/output/...` while the host volume location changes; arbitrary path relocation requires an explicit migration and is not claimed here.

## Backup and restoration boundary

Stop the single Ghostwriter application process before copying SQLite and its associated files. Snapshot the three Compose volumes together: `ghostwriter_data` (`/app/data`, including database and account token files), `ghostwriter_epubs` (`/app/output`, including PDFs, covers and podcasts), and `ghostwriter_logs` (`/app/logs`). If the optional sidecar is used, include `ollama_data` (`/root/.ollama`) when its state is needed. Copy deployment configuration and secrets separately into protected operator storage; never add them to this repository or PR evidence.

Restore into new volumes/directories first and retain the untouched backup. Run migrations before starting the application. After feed sync v2 is enabled, follow the server identity-rotation procedure in `RELEASE.md` before accepting mutations from existing clients. A backup may contain an old instance ID and mutation receipt history; returning those to service without rotation can accept stale client intent. The integrated final readiness check must exercise this command and rejection of a pre-restore client request.

Do not run an older binary against a v2 database. Binary rollback requires restoring the matching pre-upgrade database and volumes, with no newer process writing them. SQLite downgrade functions intentionally do not drop columns or reverse data semantics.

## Runtime and remaining acceptance

The container entrypoint runs migrations then one Uvicorn process. Scheduling and generation locks are in-process; running additional Uvicorn workers or overlapping application replicas is outside the verified architecture. The optional Ollama process does not coordinate Ghostwriter jobs. Keep the old instance stopped throughout restore/cutover.

The historical 1.1.0 notes remain historical; later schema, narration/chapter, and reliability changes are unreleased. Local backend/browser/native tests and hosted amd64 image health checks do not establish registry visibility, arm64 execution, real provider quality, device scheduling, signing or store distribution. Before choosing a release, the owner still needs to name the release surfaces and public-versus-authenticated registry pull policy. These checks neither publish an image nor authorize a deployment.
