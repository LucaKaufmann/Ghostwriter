<p align="center">
  <img src="Ghostwriter_banner.png" alt="Ghostwriter" />
</p>

# Ghostwriter

Ghostwriter is the repository for a cross-platform RSS-to-EPUB workflow for focused reading, with optional AI-narrated podcast generation.

- Epilogue mobile apps (Android + iOS) manage feeds and read digests.
- Ghostwriter (self-hosted backend) generates digests, runs schedules, syncs across devices, and produces podcast episodes from your content.

If you want to try the project quickly, start with Ghostwriter.

## Why Ghostwriter

- Build a daily reading digest from RSS/Atom feeds.
- `Fidelity` mode for full-article extraction.
- `Briefing` mode for AI summaries.
- Read generated EPUBs on e-ink devices, phones, or tablets.
- **Generate AI-narrated podcast episodes** from your digests using ElevenLabs TTS.
- Subscribe via a standards-compliant RSS podcast feed in your favorite podcast app.
- Choose between two-host conversational or single-host monologue narration styles.
- Optionally sync feeds and digests through a self-hosted backend.

## Project Layout

- `app/`: Epilogue Android app (Kotlin, Compose, Room, WorkManager).
- `EpilogueIOS/`: Epilogue iOS app (Swift, SwiftUI, Tuist modules).
- `ghostwriter/`: FastAPI backend + Svelte web UI, including podcast generation pipeline and TTS integration.
- `docs/`, `examples/`: project docs and sample files.

## Ghostwriter Quick Start (Docker)

### Prerequisites

- Docker + Docker Compose
- An API key for [OpenAI](https://platform.openai.com/api-keys) or [Google Gemini](https://aistudio.google.com/apikey), unless you use Ollama

### 1. Configure Environment

```bash
cd ghostwriter
cp .env.example .env
```

Edit `.env` and set the one provider credential you want to use. Most users only need:

```bash
OPENAI_API_KEY=sk-...
```

Optional but useful:

```bash
TIMEZONE=Europe/Helsinki
# JWT_SECRET=...  # recommended if you want logins to survive restarts
```

For Gemini or Ollama, switch to the alternative provider block already shown in [`ghostwriter/.env.example`](ghostwriter/.env.example). For podcast generation, configure your ElevenLabs API key and TTS preferences in the web UI under Settings.

### 2. Start Ghostwriter

```bash
docker compose up -d
```

### 3. Verify and Open

```bash
curl http://localhost:8080/health
```

Open [http://localhost:8080](http://localhost:8080).

On first run:

1. Create the first user account (becomes admin).
2. Generate API tokens in `Settings -> API Tokens` for mobile clients.

### Using Ollama (Local AI)

To use a local Ollama instance instead of a cloud API:

```bash
# Switch to the Ollama block in .env, then:
docker compose --profile with-ollama up -d

# Pull a model (first run only)
docker exec ollama ollama pull llama3.2
```

## Ghostwriter Releases

Ghostwriter Docker images are published to `ghcr.io/lucakaufmann/ghostwriter`.
Stable container releases come from git tags named `ghostwriter-vX.Y.Z`, which publish versioned tags plus `latest`.

To run the published image from the repo checkout:

```bash
cd ghostwriter
cp .env.example .env
docker compose pull
docker compose up -d
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

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions and guidelines.

## License

This project is licensed under the [GNU General Public License v3.0](LICENSE). See [NOTICE](NOTICE) for third-party attribution.
