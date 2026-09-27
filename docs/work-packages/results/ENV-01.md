# ENV-01 result

Status: verified and independently reviewed; ready for PR.

- Base: `e6e62677fe4f5b8f516e226a48080008cafc04e0` (`origin/main`).
- Head: the scoped commits carrying this result (SHAs in the PR and final handoff).
- Package metadata now declares the runtime libraries used by authentication, migrations, YouTube, podcast metadata, and scheduling. Docker's standalone `requirements.txt` remains a compatible runtime install path, enforced by a manifest test.
- SQLModel is constrained to `<0.0.32`: fresh installs of 0.0.46 and 0.0.47 failed existing database writes with `Datetime values must have timezone information`; 0.0.31 passed. This is a compatibility bound, not a model or schema change.
- `youtube-transcript-api` now requires `>=1.0.0,<2.0.0`, matching the [upstream v1.0.0 API change](https://github.com/jdepoix/youtube-transcript-api/releases/tag/v1.0.0) that introduced instance `fetch`/`list` and object snippets. With installed 1.2.4, an offline real-library boundary test verifies English, other-language, and empty captions. The other-language path now reads the first item from the library's iterable `TranscriptList`.
- Test configuration disables Pydantic and LiteLLM dotenv loading before app import, clears case variants of host integration settings, uses temporary storage, disables scheduling, and blocks real DNS/IP connections. It restores host environment, settings configuration, and socket functions when an in-process pytest run ends. Feed tests use an explicit public DNS answer; literal IPs are resolved synthetically so existing URL validation tests remain meaningful.

## Verification

Python 3.11.16, separate disposable virtual environments:

- `.venv/bin/python -m pip install -e '.[dev]'`: passed.
- `.venv/bin/python -m pip check`: passed.
- `.venv/bin/python -m pytest -q`: 252 passed, 2 listed warnings with YouTube API 1.2.4.
- Full suite from a temporary working directory containing a synthetic sentinel `.env` with mixed-case provider and lowercase private-host settings: 252 passed, 2 listed warnings; no sentinel provider key, scheduler setting, private-host opt-in, or data path entered app settings. The isolation test also checks mixed-case host settings are restored after nested pytest.
- In a second clean environment, `python -m pip install -r requirements.txt`: passed; `pip check`: passed; `pytest --collect-only -q`: 251 tests collected before the added case-variant regression, including podcast and YouTube boundary tests. YouTube API 1.2.4 resolved. Environment removed afterward.
- `.venv/bin/ruff check tests/conftest.py tests/test_feeds.py tests/test_dependency_metadata.py tests/test_youtube_dependency_contract.py app/services/youtube_service.py --ignore UP041`: passed. `UP041` is an existing `asyncio.TimeoutError` alias outside this change.
- `git diff --check`: passed.
- Root's combined integration checkout: 264 backend tests passed with 3 baseline warnings, and 15 helper tests passed. Final independent Sol review of the implementation commit `3724701fcf893ad25169aa162199192d3ff9f439` exited cleanly with no findings.

The two listed warnings are an upstream Starlette deprecation and a Pydantic typed-dict warning. An existing AsyncMock test intermittently emits an additional unraisable-coroutine warning after the progress line. WeasyPrint host libraries and optional local media executables are documented in `ghostwriter/README.md`. `ffmpeg -version` reported 8.1 locally; `yt-dlp` and `whisper-cli` were absent, so no audio end-to-end call or Docker image build was run. No schema migration was needed.

## Review and next action

Independent Sol review identified host-state restoration, UDP `sendmsg`, dependency API, and case-insensitive environment gaps; all were fixed and regression-tested. The final review and combined checks passed. Publish the scoped PR; no deployment, merge, or provider calls performed.
