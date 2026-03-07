# Epilogue

Epilogue is a cross-platform RSS-to-EPUB workflow for focused reading — with optional AI-narrated podcast generation.

- Mobile apps (Android + iOS) manage feeds and read digests.
- Ghostwriter (self-hosted backend) generates digests, runs schedules, syncs across devices, and produces podcast episodes from your content.

If you want to try the project quickly, start with Ghostwriter.

## Why Epilogue

- Build a daily reading digest from RSS/Atom feeds.
- `Fidelity` mode for full-article extraction.
- `Briefing` mode for AI summaries.
- Read generated EPUBs on e-ink devices, phones, or tablets.
- **Generate AI-narrated podcast episodes** from your digests using ElevenLabs TTS.
- Subscribe via a standards-compliant RSS podcast feed in your favorite podcast app.
- Choose between two-host conversational or single-host monologue narration styles.
- Optionally sync feeds and digests through a self-hosted backend.

## Project Layout

- `app/`: Android app (Kotlin, Compose, Room, WorkManager).
- `EpilogueIOS/`: iOS app (Swift, SwiftUI, Tuist modules).
- `ghostwriter/`: FastAPI backend + Svelte web UI, including podcast generation pipeline and TTS integration.
- `docs/`, `examples/`: project docs and sample files.

## Ghostwriter Quick Start (Docker)

### Prerequisites

- Docker + Docker Compose

### 1. Configure Environment

```bash
cd ghostwriter
cp .env.example .env
```

Edit `.env` as needed (AI provider, timezone, schedule, credentials). For podcast generation, configure your ElevenLabs API key and TTS preferences in the web UI under Settings.

### 2. Start Services

```bash
docker compose up -d
```

This starts Ghostwriter and an Ollama sidecar by default.

### 3. Pull the Default Ollama Model (First Run)

```bash
docker exec ollama ollama pull llama3.2
```

### 4. Verify and Open

```bash
curl http://localhost:8080/health
```

Open [http://localhost:8080](http://localhost:8080).

On first run:

1. Create the first user account (becomes admin).
2. Generate API tokens in `Settings -> API Tokens` for mobile clients.

### Cloud AI Only (No Ollama)

```bash
cd ghostwriter
cp .env.example .env
# set AI_PROVIDER=openai (or gemini) and required API key(s) in .env
docker compose -f docker-compose.cloud.yml up -d
```

## Ghostwriter Local Development

Backend:

```bash
cd ghostwriter
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8080
```

Frontend (separate terminal):

```bash
cd ghostwriter/frontend
npm install
npm run dev
```

The frontend dev server proxies `/api` to `http://localhost:8080`.

## Mobile App Setup

### Android

Requirements:

- Android 13+ (API 33+)
- JDK 17

Build and test:

```bash
./gradlew assembleDebug
./gradlew test
```

### iOS

Requirements:

- iOS 18.0+
- Xcode 17+
- Tuist

Build:

```bash
cd EpilogueIOS
tuist install
tuist generate
xcodebuild -workspace Epilogue.xcworkspace -scheme Epilogue build
```

## Development Commands

- Android release build: `./gradlew assembleRelease`
- Android Google Play upload (local script): `scripts/upload_play_release.sh --version-code 42 --version-name 1.0.0 --track internal`
- Android tests: `./gradlew test`
- iOS workspace generation: `cd EpilogueIOS && tuist install && tuist generate`
- Ghostwriter backend tests: `cd ghostwriter && pytest`
- Ghostwriter frontend type checks: `cd ghostwriter/frontend && npm run check`
- Ghostwriter frontend production build: `cd ghostwriter/frontend && npm run build`

## Notes Before Open Sourcing

- A root `LICENSE` file is not present yet. Add one before publishing publicly.
- Screenshots and demo media are not included yet; adding them will improve first impressions.

## Contributing

Contributions are welcome. For now, use small focused PRs with clear test notes.
