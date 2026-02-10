# Repository Guidelines

## Workflow Orchestration
### Plan Mode Default
- Enter plan mode for any non-trivial task (3+ steps or architectural decisions).
- If something goes sideways, stop and re-plan immediately. Do not keep pushing.
- Use plan mode for verification steps, not just building.
- Write detailed specs up front to reduce ambiguity.

### Subagent Strategy
- Use subagents liberally to keep the main context window clean.
- Offload research, exploration, and parallel analysis to subagents.
- For complex problems, throw more compute at it via subagents.
- One task per subagent for focused execution.

### Self-Improvement Loop
- After any correction from the user, update `tasks/lessons.md` with the pattern.
- Write rules for yourself that prevent the same mistake.
- Ruthlessly iterate on these lessons until the mistake rate drops.
- Review lessons at session start for the relevant project.

### Verification Before Done
- Never mark a task complete without proving it works.
- Diff behavior between main and your changes when relevant.
- Ask yourself: "Would a staff engineer approve this?"
- Run tests, check logs, demonstrate correctness.

### Demand Elegance (Balanced)
- For non-trivial changes, pause and ask "is there a more elegant way?"
- If a fix feels hacky: "Knowing everything I know now, implement the elegant solution."
- Skip this for simple, obvious fixes. Do not over-engineer.
- Challenge your own work before presenting it.

### Autonomous Bug Fixing
- When given a bug report: just fix it. Do not ask for hand-holding.
- Point at logs, errors, failing tests, then resolve them.
- Zero context switching required from the user.
- Go fix failing CI tests without being told how.

### Task Management
1. **Plan First**: Write plan to `tasks/todo.md` with checkable items.
2. **Verify Plan**: Check in before starting implementation.
3. **Track Progress**: Mark items complete as you go.
4. **Explain Changes**: High-level summary at each step.
5. **Document Results**: Add review section to `tasks/todo.md`.
6. **Capture Lessons**: Update `tasks/lessons.md` after corrections.

### Core Principles
- **Simplicity First**: Make every change as simple as possible. Impact minimal code.
- **No Laziness**: Find root causes. No temporary fixes. Senior developer standards.
- **Minimal Impact**: Changes should only touch what's necessary. Avoid introducing bugs.

## Project Structure & Module Organization
- `app/`: Android app (Kotlin, Compose, MVVM, Room, WorkManager).
- `EpilogueIOS/`: iOS app (Swift, SwiftUI, Tuist workspace).
- `ghostwriter/`: Python FastAPI server + Svelte frontend (`ghostwriter/frontend/`).
- `docs/`, `examples/`: supporting docs and samples.

## Build, Test, and Development Commands
- Android build: `./gradlew assembleDebug` (debug APK), `./gradlew assembleRelease` (release APK).
- Android tests: `./gradlew test` (unit tests), `./gradlew connectedAndroidTest` (instrumented).
- iOS setup: `cd EpilogueIOS && tuist install && tuist generate`.
- iOS build: `xcodebuild -workspace Epilogue.xcworkspace -scheme Epilogue build`.
- Ghostwriter backend install: `cd ghostwriter && pip install -r requirements.txt`.
- Ghostwriter backend dev server: `uvicorn app.main:app --reload --port 8080`.
- Ghostwriter Docker: `cd ghostwriter && docker compose up -d`
- Ghostwriter frontend install: `cd ghostwriter/frontend && npm install`.
- Ghostwriter frontend dev: `npm run dev` (local dev).
- Ghostwriter frontend build: `npm run build` (production build).
- Ghostwriter frontend checks: `npm run check` (typecheck).
- Ghostwriter tests: `cd ghostwriter && pytest`

## Coding Style & Naming Conventions
- Indentation: 4 spaces for Kotlin, Swift, and Python; 2 spaces for Svelte/TS in `ghostwriter/frontend/`.
- Python: `ruff` (line length 88) and `mypy` are configured in `ghostwriter/pyproject.toml`.
- Keep file and type names consistent with platform norms: `PascalCase` for Kotlin/Swift types, `snake_case` for Python.

## Testing Guidelines
- Android unit tests live in `app/src/test/` and use JUnit4 + MockK.
- iOS tests live under `EpilogueIOS/**/Tests/` and use XCTest.
- Ghostwriter tests live in `ghostwriter/tests/` and use `pytest` + `pytest-asyncio`.
- Naming: `*Test.kt`, `*_tests.py`, `*Tests.swift`.

## Commit & Pull Request Guidelines
- Commit messages must follow Conventional Commits (e.g. `feat: ...`, `fix: ...`, `perf: ...`, `tweak: ...`).
- PR titles must also follow Conventional Commits format.
- Keep commits scoped and descriptive; include a short summary of behavior changes.
- PRs should include: summary, testing performed, and screenshots for UI changes (Android, iOS, or Ghostwriter web).

## Ghostwriter Database Migrations

**Alembic is the only migration system.** Do not create standalone scripts in `scripts/`.

### When You Change a Database Schema

If you add, remove, or modify a column/table/index in any SQLModel under `ghostwriter/app/models/`, you MUST also create an Alembic migration. Two things to update:

1. **The model** (`app/models/*.py`) — source of truth for the schema.
2. **An Alembic migration** (`alembic/versions/NNN_description.py`) — applies the change to existing databases.

Forgetting the migration means existing deployments won't get the new column and will break at runtime. `create_all()` only creates missing **tables**, it does NOT add columns to existing tables.

### How to Write a Migration

Create `ghostwriter/alembic/versions/NNN_description.py` where `NNN` is the next sequential number. Template:

```python
"""Short description.

Revision ID: NNN
Revises: (N-1)
Create Date: YYYY-MM-DD
"""
from typing import Sequence, Union
from alembic import context, op
import sqlalchemy as sa

revision: str = "NNN"
down_revision: Union[str, None] = "(N-1)"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    if context.get_context().dialect.name != "sqlite":
        return

    conn = op.get_bind()
    result = conn.execute(sa.text("PRAGMA table_info(table_name)"))
    existing = {row[1] for row in result}

    if "new_column" not in existing:
        op.execute(
            "ALTER TABLE table_name ADD COLUMN new_column TYPE DEFAULT value"
        )

def downgrade() -> None:
    pass  # No-op for SQLite — never drop columns in production
```

### Rules

- **Idempotent**: Always check if column/index exists before creating. Use `PRAGMA table_info()` for columns, query `sqlite_master` for indexes.
- **No DROP COLUMN**: `downgrade()` should be `pass`.
- **Making columns nullable**: Use `op.batch_alter_table()`:
  ```python
  with op.batch_alter_table("table") as batch_op:
      batch_op.alter_column("col", existing_type=sa.String(32), nullable=True)
  ```
- **Sequential revision IDs**: `"007"`, `"008"`, etc. Check `ghostwriter/alembic/versions/` for current head.
- **New model files**: Add import to `ghostwriter/alembic/env.py`.
- **Test both paths**: fresh DB (no tables) and existing DB at previous revision.

### What NOT to Do

- Do NOT create standalone migration scripts in `scripts/`.
- Do NOT add hardcoded `ALTER TABLE` to `init_db()` in `database.py`.
- Do NOT use `--autogenerate` without reviewing the output — it produces incorrect migrations for SQLite.
- Do NOT skip the migration when adding a model column.

### Deployment

Migrations run automatically on container start (`entrypoint.sh` → `alembic upgrade head`).

- Deploy to Pi: `./ghostwriter/deploy.sh pi`
- Deploy to Synology: `./ghostwriter/deploy.sh synology`
- Deploy to Mac (dev): `./ghostwriter/deploy.sh mac`

## Security & Configuration Tips
- Do not commit secrets. Use `ghostwriter/.env` from `.env.example` and keep credentials local.
- Android uses `local.properties` for SDK paths; iOS secrets are stored in Keychain at runtime.

## Mac Dev Environment (Ghostwriter)
- Local dev directory: `/path/to/ghostwriter`
- Compose file: `/path/to/ghostwriter/docker-compose.yml`
- Env file: `/path/to/ghostwriter/.env`
- Data: `/path/to/ghostwriter/data`
- EPUBs: `/path/to/ghostwriter/epubs`
- Logs: `/path/to/ghostwriter/logs`
- Deploy (mac): `ghostwriter/deploy.sh mac`
- Access: `http://localhost:8080`
- Container logs: `docker logs -f ghostwriter-dev`
