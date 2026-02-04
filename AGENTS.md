# Repository Guidelines

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
- Commit messages generally follow a conventional pattern: `feat: ...`, `fix: ...`, `perf: ...`, `tweak: ...` (lowercase preferred).
- Keep commits scoped and descriptive; include a short summary of behavior changes.
- PRs should include: summary, testing performed, and screenshots for UI changes (Android, iOS, or Ghostwriter web).

## Security & Configuration Tips
- Do not commit secrets. Use `ghostwriter/.env` from `.env.example` and keep credentials local.
- Android uses `local.properties` for SDK paths; iOS secrets are stored in Keychain at runtime.

## Mac Dev Environment (Ghostwriter)
- Local dev directory: `/Users/luca/docker/ghostwriter`
- Compose file: `/Users/luca/docker/ghostwriter/docker-compose.yml`
- Env file: `/Users/luca/docker/ghostwriter/.env`
- Data: `/Users/luca/docker/ghostwriter/data`
- EPUBs: `/Users/luca/docker/ghostwriter/epubs`
- Logs: `/Users/luca/docker/ghostwriter/logs`
- Deploy (mac): `ghostwriter/deploy.sh mac`
- Access: `http://localhost:8159`
- Container logs: `docker logs -f ghostwriter-dev`
