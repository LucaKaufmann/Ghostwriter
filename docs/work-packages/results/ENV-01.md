# ENV-01 result

Status: implementation verified locally; pending orchestrator review and PR.

- Base: `e6e62677fe4f5b8f516e226a48080008cafc04e0` (`origin/main`).
- Head: the scoped commits carrying this result (SHAs in the PR and final handoff).
- Package metadata now declares the runtime libraries used by authentication, migrations, YouTube, podcast metadata, and scheduling. Docker's standalone `requirements.txt` remains a compatible runtime install path, enforced by a manifest test.
- SQLModel is constrained to `<0.0.32`: fresh installs of 0.0.46 and 0.0.47 failed existing database writes with `Datetime values must have timezone information`; 0.0.31 passed. This is a compatibility bound, not a model or schema change.
- Test configuration disables Pydantic and LiteLLM dotenv loading before app import, clears host integration settings, uses temporary storage, disables scheduling, and blocks real DNS/IP connections. It restores host environment, settings configuration, and socket functions when an in-process pytest run ends. Feed tests use an explicit public DNS answer; literal IPs are resolved synthetically so existing URL validation tests remain meaningful.

## Verification

Python 3.11.16, separate disposable virtual environments:

- `.venv/bin/python -m pip install -e '.[dev]'`: passed.
- `.venv/bin/python -m pip check`: passed.
- `.venv/bin/python -m pytest -q`: 248 passed, 3 warnings after review fixes.
- Full suite from a temporary working directory containing a synthetic sentinel `.env`: 248 passed, 3 warnings; no sentinel provider key, scheduler setting, or data path entered app settings. The revised isolation test also checks sentinel host settings are restored after nested pytest.
- In a second clean environment, `python -m pip install -r requirements.txt`: passed; `pip check`: passed; `pytest --collect-only -q`: 247 tests collected before the review regression test was added, including podcast tests. Environment removed afterward.
- `.venv/bin/ruff check tests/conftest.py tests/test_feeds.py tests/test_dependency_metadata.py`: passed.
- `git diff --check`: passed.

The warnings are an upstream Starlette deprecation, a Pydantic typed-dict warning, and an intermittent unawaited AsyncMock warning from an existing test. WeasyPrint host libraries are documented in `ghostwriter/README.md`; this check did not perform provider/audio end-to-end calls or a Docker image build. No schema migration was needed.

## Review and next action

Independent Sol review identified host-state restoration and UDP `sendmsg` gaps; both were fixed and regression-tested. Pending root's review rerun/integration check, then publish the scoped PR. No deployment, merge, or provider calls performed.
