# RUNTIME-01 result

Status: accepted for the verified amd64 runtime; arm64 remains unverified.
Base: `de68d540ea67383a3843b8085659d29dcf19baaa` (ENV-01). Branch:
`codex/runtime-01-controlled-build`. The exact final commit is reported in
the PR/orchestrator handoff after this file is committed.

The image now builds whisper.cpp at release `v1.8.7`'s full commit
`48f628a84833905ee4a0658ee6d4a5c915ce1997`, checks out and verifies
that commit, and fails if its CMake build or `strip` fails. `GGML_NATIVE=OFF`
avoids builder-specific CPU instructions; arm64 retains an armv8-a baseline.
The image installs the exact yt-dlp 2026.8.19 wheel with its PyPI SHA-256
check via `build-constraints.txt`. Python 3.12 and Node 24 now match the
existing Ghostwriter PR check runtime lines. The image build checks that
`whisper-cli --help` and `yt-dlp --version` run. There are no schema or app
behavior changes.

## Checks

| Command / check | Result |
| --- | --- |
| `git ls-remote ... refs/tags/v1.8.7`; direct `git fetch --depth=1 origin 48f628a...` | Passed; tag and fetched commit resolve to the full SHA above. |
| Inspect pinned upstream CMake/CLI source | Passed; `whisper-cli` target, shared library paths, `GGML_NATIVE`, and `--help` exit path confirmed. This is source inspection, not a Linux binary run. |
| Python 3.12.2 isolated venv: `pip install -r requirements.txt` | Passed. |
| Same venv: `pip install --no-cache-dir --only-binary=:all: --no-deps --require-hashes -r build-constraints.txt`; `yt-dlp --version` | Passed; hash verified, reported `2026.08.19`. |
| Same venv: `pytest -q tests/test_health.py tests/test_alembic_bootstrap.py tests/test_podcast_multi_digest_migration.py tests/test_digest_download_formats.py tests/test_youtube_service.py tests/test_transcription_service.py --durations=10` | Passed, 33 tests. Existing deprecation and AsyncMock warnings remain. |
| Synthetic fresh host data: `alembic upgrade head`; `alembic current` | Passed, revision `025 (head)`. |
| Synthetic host startup: Python 3.12 `uvicorn`, `SCHEDULE_ENABLED=false`, local model cost map, local `/health` | Passed, `{"status":"healthy"}`; startup used fresh temporary data/output/log paths and no provider credentials. The first sandboxed attempt could not bind localhost; the permitted retry passed. |
| Node 24.21.0: `npm ci --offline`, `npm run check`, `npm run build` | Passed; Svelte check reported zero errors/warnings. |
| `docker version`, `docker buildx ls`, `docker buildx build --platform linux/arm64 --load -t ghostwriter-runtime-check:arm64 .` | Blocked: Docker daemon unavailable. No image was built. `linux/amd64` was not attempted for the same reason. |

Local Docker remains unavailable. Hosted CI at implementation commit `48cb611`
built the amd64 image and passed its actual startup/migration health smoke
([run36313233006](https://github.com/LucaKaufmann/Ghostwriter/actions/runs/36313233006));
the Dockerfile binary/yt-dlp checks passed as part of that build. Hosted backend
and frontend checks passed in run36313232980. Arm64 has not been built or run. The Dockerfile's runtime commands will fail the image build if the
binary or wheel check fails. PR83 carries this evidence and the architecture limitation. No registry push, release, deployment,
production mount, model download, or paid transcription was performed.

## Review

Final independent Sol branch review against ENV-01 returned no actionable findings.

Scoped review found and fixed the prior `cmake ... && strip ... || true` chain,
which could hide any CMake failure. The new `set -eu` chain fails the build on
fetch, checkout, configure, compile, or strip errors. The pinned release's
CLI `--help` returns zero. Remaining mutable inputs are documented in
`ghostwriter/docs/build-inputs.md`; this is not bit-for-bit reproducibility.
