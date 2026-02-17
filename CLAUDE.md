# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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

## Commit & Pull Request Guidelines
- Commit messages must follow Conventional Commits (e.g. `feat: ...`, `fix: ...`, `perf: ...`, `tweak: ...`).
- PR titles must also follow Conventional Commits format.
- Keep commits scoped and descriptive; include a short summary of behavior changes.
- PRs should include: summary, testing performed, and screenshots for UI changes (Android, iOS, or Ghostwriter web).

## Project Overview

Epilogue is a multiplatform application (Android + iOS) that aggregates RSS/Atom feeds, Wallabag bookmarks, and Gmail newsletters, processes content through either full extraction or AI summarization, and compiles results into daily EPUB files for offline reading on e-ink devices (optimized for Onyx Boox Palma 2). A Python FastAPI backend (Ghostwriter) handles remote digest generation, and a shared Kotlin Multiplatform (KMP) module provides a unified networking layer across Android and iOS.

## Build Commands

**Important:** Set JAVA_HOME to Android Studio's bundled JDK before running Gradle:
```bash
export JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home"
```

### Android + Shared Module
```bash
./gradlew build              # Build entire project (app + shared)
./gradlew assembleDebug      # Build debug APK
./gradlew assembleRelease    # Build release APK
./gradlew test               # Run all unit tests (app + shared)
./gradlew connectedAndroidTest  # Run instrumented tests
./gradlew lint               # Run lint checks
./gradlew clean              # Clean build artifacts
```

### Shared KMP Module Only
```bash
./gradlew :shared:assemble   # Build shared module (all targets)
./gradlew :shared:check      # Run shared module tests
```

### iOS XCFramework
```bash
./gradlew :shared:assembleEpilogueSharedDebugXCFramework    # Debug XCFramework
./gradlew :shared:assembleEpilogueSharedReleaseXCFramework  # Release XCFramework
```
Output: `shared/build/XCFrameworks/{debug,release}/EpilogueShared.xcframework`

Run a single test:
```bash
./gradlew test --tests "com.example.epilog.ExampleUnitTest"
```

## ADB Commands

ADB path on this machine:
```bash
adb
```

```bash
adb devices                    # List connected devices
adb install -r app/build/outputs/apk/debug/app-debug.apk  # Install debug APK
adb shell am start -n com.example.epilogue/.ui.MainActivity  # Launch app
adb logcat -s "Epilogue:*"     # View app logs
```

For targeting a specific device (e.g., Palma 2), use `-s <device_id>`:
```bash
adb -s <device_id> install -r app/build/outputs/apk/debug/app-debug.apk
```

## Tech Stack

- **Language:** Kotlin (Android + shared), Swift (iOS)
- **Min SDK:** Android 13+ / iOS 18.0
- **UI:** Jetpack Compose with Material 3 (Android), SwiftUI (iOS)
- **Architecture:** MVVM with Clean Architecture
- **Shared Layer:** Kotlin Multiplatform (KMP) for Ghostwriter networking
- **DI:** Hilt (Android)
- **Async:** Coroutines & Flow (Android + shared), Swift Concurrency (iOS)
- **Database:** Room (Android), SwiftData (iOS)
- **Background:** WorkManager (Android), BGTaskScheduler (iOS)

### Key Libraries
- `Retrofit` + `OkHttp` (60s timeouts for slow scraping) - Android legacy networking
- `Ktor` - shared KMP HTTP client (OkHttp engine on Android, Darwin/URLSession on iOS)
- `kotlinx.serialization` - shared JSON serialization
- `Readability4J` (net.dankito.readability4j) for article extraction
- `Jsoup` for HTML parsing
- `RSS-Parser` (com.prof18.rssparser) for feed parsing
- `Epublib` (nl.siegmann.epublib) for EPUB generation

## Architecture

### High-Level Overview

```
┌─────────────────┐     ┌─────────────────┐     ┌──────────────────┐
│   Android App   │     │    iOS App       │     │  Ghostwriter Web │
│  (Jetpack       │     │  (SwiftUI)       │     │  (SvelteKit)     │
│   Compose)      │     │                  │     │                  │
└────────┬────────┘     └────────┬─────────┘     └────────┬─────────┘
         │                       │                         │
         │  ┌────────────────────┴──────────┐              │
         │  │                               │              │
         ▼  ▼                               │              │
┌─────────────────────┐                     │              │
│   :shared (KMP)     │                     │              │
│  ┌───────────────┐  │                     │              │
│  │ Ghostwriter   │  │                     │              │
│  │ ApiClient     │  │                     │              │
│  │ (Ktor)        │  │                     │              │
│  ├───────────────┤  │                     │              │
│  │ Shared DTOs   │  │                     │              │
│  │ (kotlinx.ser) │  │                     │              │
│  └───────────────┘  │                     │              │
└──────────┬──────────┘                     │              │
           │                                │              │
           ▼                                ▼              ▼
    ┌──────────────────────────────────────────────────────────┐
    │              Ghostwriter Backend (FastAPI)                │
    │                  ghostwriter/                             │
    └──────────────────────────────────────────────────────────┘
```

### Shared KMP Module (`shared/`)

The `:shared` Gradle module contains Kotlin Multiplatform code that compiles to both an Android library and an iOS XCFramework (`EpilogueShared.xcframework`). It currently provides the Ghostwriter API client layer, giving both platforms identical networking behavior, error handling, and DTO serialization.

```
shared/
├── build.gradle.kts                          # KMP plugin, targets, dependencies
└── src/
    ├── commonMain/kotlin/.../ghostwriter/
    │   ├── CoreModels.kt                     # All Ghostwriter DTOs (@Serializable)
    │   ├── GhostwriterApiClient.kt           # Ktor-based API client + error hierarchy
    │   ├── GhostwriterClientHandle.kt        # Lifecycle wrapper (HttpClient + ApiClient)
    │   └── PlatformHttpClient.kt             # expect fun createPlatformHttpClient()
    ├── commonTest/kotlin/.../ghostwriter/
    │   ├── CoreModelsSerializationTest.kt     # JSON wire-format round-trip tests
    │   └── GhostwriterApiClientTest.kt        # URL construction, auth, query param tests
    ├── androidMain/kotlin/.../ghostwriter/
    │   └── PlatformHttpClient.android.kt      # actual impl: OkHttp engine
    └── iosMain/kotlin/.../ghostwriter/
        └── PlatformHttpClient.ios.kt          # actual impl: Darwin/URLSession engine
```

**Key classes:**

- **`GhostwriterApiClient`** - Ktor-based HTTP client with methods for every Ghostwriter endpoint. Handles URL normalization (auto-appends `/api/`), auth headers, and maps HTTP errors to a `GhostwriterApiException` sealed hierarchy (Unauthorized, NotFound, Conflict, RateLimited, HttpError).
- **`GhostwriterClientHandle`** - Owns the `HttpClient` + `GhostwriterApiClient` pair. Call `create(baseUrl, apiKey)` to instantiate and `close()` to dispose. This is the entry point for both platforms.
- **`CoreModels.kt`** - All DTOs use `@Serializable` with `@SerialName` for snake_case wire format. These are the single source of truth for the Ghostwriter API contract.

**Platform HTTP configuration** (both platforms):
- 30s request timeout, 15s connect timeout
- 2 retries with exponential backoff on server errors and 429
- `ignoreUnknownKeys = true` for forward compatibility

### How the Shared Module Integrates

**Android** (`app/` depends on `:shared`):
- `SharedGhostwriterAdapter` wraps the shared client and maps KMP DTOs to existing Android app DTOs via `.toApp()` extension functions
- `GhostwriterRepository` checks `shouldUseSharedClient()` at the top of every method; if enabled, delegates to the adapter, otherwise falls back to the legacy Retrofit path
- Feature flag: `SettingsRepository.useSharedGhostwriterClient()` (persisted in SharedPreferences)

**iOS** (`EpilogueIOS/Modules/GhostwriterClient/` depends on `EpilogueShared.xcframework`):
- `GhostwriterClient.swift` uses `#if canImport(EpilogueShared)` to conditionally delegate to the shared client
- `GhostwriterClientHandle` is constructed in the initializer and each method maps shared KotlinInt/KotlinBoolean types back to Swift native types
- Controlled by `useSharedClient: Bool` constructor parameter

### Android App Structure

```
app/
├── data/
│   ├── local/          # Room entities, DAOs
│   ├── remote/
│   │   └── ghostwriter/
│   │       ├── GhostwriterApi.kt             # Retrofit interface (legacy)
│   │       └── SharedGhostwriterAdapter.kt   # KMP shared client adapter
│   └── repository/
│       ├── GhostwriterRepository.kt          # Dual-path: shared client or Retrofit
│       └── SettingsRepository.kt             # Feature flags incl. shared client toggle
├── domain/
│   ├── model/          # Feed, ProcessedArticle
│   └── usecase/        # FetchArticlesUseCase, GenerateEpubUseCase
├── di/                 # Hilt modules
├── service/
│   ├── ContentProcessor    # Jsoup → Readability4J pipeline
│   ├── EpubGenerator       # epublib wrapper
│   ├── OpenAIService       # Briefing mode summarization
│   └── DailyDigestWorker   # WorkManager background job
└── ui/
    ├── feed/           # Feed management screens
    └── settings/       # API key, schedule configuration
```

## Data Models

```kotlin
// Feed entity - stored in Room
@Entity(tableName = "feeds")
data class Feed(
    @PrimaryKey val url: String,
    val name: String,
    val mode: ProcessingMode,  // FIDELITY or BRIEFING
    val lastFetched: Long = 0L
)

// Transient processing result
data class ProcessedArticle(
    val title: String,
    val author: String,
    val content: String,  // HTML or Markdown
    val originalUrl: String,
    val isSummary: Boolean
)
```

## Processing Modes

1. **FIDELITY**: Full article extraction via Readability4J, preserves structure, strips ads/sidebars. Optional filter for articles <300 words.

2. **BRIEFING**: AI summarization via OpenAI API. Output structure: Hook, Key Details, Significance. Uses "neutral editor" tone.

## EPUB Output

- Location: `/Documents/Epilogue/`
- Naming: `Epilogue_YYYY-MM-DD.epub`
- Structure: Cover → TOC → Section 1 (Briefings) → Section 2 (Full Articles)
- **Critical**: Must call `MediaScannerConnection` after save for Boox Library visibility

## E-ink UI Constraints

- Pure black (#000000) on white (#FFFFFF) only
- No animations (disable `windowAnimationScale` or Compose animations)
- High-legibility serif font (Merriweather recommended)

## Jetpack Compose Layout Patterns

### Scaffold innerPadding with Lists

When using `Scaffold` with a `LazyColumn` that should extend to the bottom of the screen, **do not** apply the full `innerPadding` to the content container. The `innerPadding` includes both top padding (for the TopAppBar) and bottom padding (for system navigation bars), which creates a large gap at the bottom of scrollable lists.

**Problem pattern (creates gap at bottom):**
```kotlin
Scaffold(topBar = { ... }) { innerPadding ->
    Box(modifier = Modifier.padding(innerPadding)) {
        LazyColumn { ... }
    }
}
```

**Correct pattern (list extends to bottom):**
```kotlin
Scaffold(topBar = { ... }) { innerPadding ->
    Box(modifier = Modifier.padding(top = innerPadding.calculateTopPadding())) {
        LazyColumn(
            contentPadding = PaddingValues(
                start = 16.dp,
                end = 16.dp,
                top = 8.dp,
                bottom = 8.dp  // Small fixed padding, not innerPadding.calculateBottomPadding()
            )
        ) { ... }
    }
}
```

This approach:
1. Applies only top padding to the Box (accounts for TopAppBar)
2. Uses small fixed bottom padding in LazyColumn's contentPadding
3. Allows the list to scroll close to the navigation bar without a large gap

## Background Execution

WorkManager `PeriodicWorkRequest` with constraints:
- `NetworkType.CONNECTED`
- `BatteryNotLow`

## API Key Storage

Store OpenAI API key in `EncryptedSharedPreferences`.

## Ghostwriter Backend

The `ghostwriter/` directory contains a Python FastAPI backend that runs on a server (Synology NAS) to generate digests remotely.

### Local Development

```bash
cd ghostwriter
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8080
```

### Docker Build & Deploy (Synology DS920+)

**Important:** The Synology DS920+ uses an Intel x86_64 CPU (linux/amd64). When building on Apple Silicon (M1/M2/M3), you must specify the target platform explicitly.

Build the Docker image:
```bash
cd ghostwriter
docker build --platform linux/amd64 -t ghostwriter:latest -t ghostwriter:$(date +%Y%m%d) .
```

Save as tar for transfer to NAS:
```bash
docker save ghostwriter:latest | gzip > ghostwriter.tar.gz
```

Transfer to Synology and load:
```bash
# Copy to NAS (via SSH, SMB, or Synology web UI)
scp ghostwriter.tar.gz user@your-server:/path/to/docker/

# SSH into NAS and load image
ssh user@your-server
docker load < /path/to/ghostwriter.tar.gz
```

Run with docker-compose on the NAS:
```bash
cd /path/to/ghostwriter
docker-compose up -d
```

Or run directly:
```bash
docker run -d \
  --name ghostwriter \
  --restart unless-stopped \
  -p 8158:8080 \
  -v ghostwriter_data:/app/data \
  -v ghostwriter_epubs:/app/output \
  -v ghostwriter_logs:/app/logs \
  -e API_KEY=your-api-key \
  -e AI_PROVIDER=gemini \
  -e GEMINI_API_KEY=your-gemini-key \
  ghostwriter:latest
```

### Database Migrations

All schema migrations use **Alembic** (`ghostwriter/alembic/`). This is the **only** migration system — do not create standalone migration scripts.

**Running migrations:**
```bash
cd ghostwriter && alembic upgrade head          # Local dev
docker exec -it ghostwriter alembic upgrade head # Docker (manual)
```
The Docker entrypoint runs `alembic upgrade head` automatically on container start.

**Creating a new migration — step by step:**

1. **Update the SQLModel** in `app/models/` first (add the column/table to the model).
2. **Create the Alembic migration:**
   ```bash
   cd ghostwriter
   alembic revision --autogenerate -m "add foo_column to bar_table"
   ```
3. **Edit the generated migration** — autogenerate often needs manual fixes for SQLite. See the pattern below.
4. **Test** with `alembic upgrade head` against both a fresh DB and an existing DB.

**Required migration pattern for SQLite:**

Every migration MUST be idempotent. SQLite does not support `ALTER COLUMN` or `DROP COLUMN`, so always check before acting:

```python
def upgrade() -> None:
    if context.get_context().dialect.name != "sqlite":
        return  # Only SQLite is used in this project

    # Check existing columns before adding
    conn = op.get_bind()
    result = conn.execute(sa.text("PRAGMA table_info(my_table)"))
    existing = {row[1] for row in result}

    if "new_column" not in existing:
        op.execute(
            "ALTER TABLE my_table ADD COLUMN new_column TEXT NOT NULL DEFAULT ''"
        )
```

For making columns nullable, use `op.batch_alter_table()` (handles the SQLite table-rebuild pattern):
```python
with op.batch_alter_table("my_table") as batch_op:
    batch_op.alter_column("col", existing_type=sa.String(32), nullable=True)
```

**Revision numbering:** Use sequential integers as revision IDs (`007`, `008`, etc.). Set `down_revision` to the previous number.

**Important:** The `downgrade()` function should be a no-op (`pass`) for SQLite — we never drop columns to avoid destructive migrations in production.

**Architecture notes:**
- `alembic/env.py` handles fresh databases automatically: detects missing `alembic_version` table, runs `create_all()` from SQLModel metadata, and stamps as head. No migration chain runs on fresh DBs.
- `init_db()` in `database.py` only calls `create_all()` — all schema evolution is in Alembic.
- All models must be imported in `alembic/env.py` for autogenerate to work.

### API Endpoints

- `GET /health` - Health check
- `GET /feeds` - List feeds
- `POST /feeds/sync` - Sync feeds from app
- `POST /digests/trigger` - Trigger digest generation
- `GET /digests` - List digests
- `GET /digests/{id}/articles` - Get articles with content
- `GET /digests/{filename}` - Download EPUB
- `GET /sync` - Combined sync endpoint (config, feeds, digests, schedules in one request)
- `GET /config` - Get client config (includes integration status)
- `PUT /config` - Update client config
- `GET /config/wallabag` - Get Wallabag configuration
- `PUT /config/wallabag` - Update Wallabag configuration
- `POST /config/wallabag/test` - Test Wallabag connection
- `POST /config/wallabag/preview` - Preview Wallabag articles
- `POST /config/wallabag/clear-seen` - Clear Wallabag seen article history
- `GET /newsletters/status` - Newsletter integration status
- `POST /newsletters/oauth/init` - Start Gmail OAuth flow
- `POST /newsletters/oauth/callback` - Exchange OAuth code for token
- `POST /newsletters/preview` - Preview newsletter articles
- `POST /config/newsletters/clear-seen` - Clear newsletter seen article history

### Integrations

Beyond RSS/Atom feeds, Ghostwriter supports two additional content sources. Both use **synthetic feed IDs** (`synthetic://wallabag`, `synthetic://newsletter`) for deduplication via the `seen_articles` table, and both can be toggled enabled/disabled independently.

#### Wallabag

Fetches unread articles from a self-hosted or SaaS Wallabag instance via OAuth2 password grant. Articles arrive with pre-extracted HTML content (no Readability extraction needed). After digest generation, articles are archived and tagged in Wallabag.

**Environment variables:** `WALLABAG_URL`, `WALLABAG_CLIENT_ID`, `WALLABAG_CLIENT_SECRET`, `WALLABAG_USERNAME`, `WALLABAG_PASSWORD`, `WALLABAG_MODE` (raw/summarize), `WALLABAG_MAX_ARTICLES`, `WALLABAG_TAG_ON_PROCESS`.

#### Gmail Newsletters

Fetches unread emails from a specified Gmail label via OAuth2 authorization code flow. HTML is cleaned for e-ink (tracking pixels, scripts, styles, unsubscribe footers removed). Emails are marked as read after processing. OAuth token stored at `data/gmail_token.json`.

**Environment variables:** `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_LABEL` (default: "Ghostwriter"), `GMAIL_MAX_ARTICLES`.

#### Sync Endpoint

`GET /sync` combines config, feeds, digests (with embedded articles), and schedules into a single response. Supports incremental sync via `feed_since` and `digest_ids` parameters. Uses direct JSON serialization (bypassing Pydantic) for performance.

### Digest Activity Logs

Ghostwriter writes detailed activity logs to `/app/logs/` (Docker volume: `ghostwriter_logs`). Logs are:
- One file per day: `ghostwriter-YYYY-MM-DD.log`
- Retained for 30 days
- Structured for both human reading and AI analysis

**Log format:**
```
[2024-01-20 07:00:00 UTC] [INFO] [scheduler] [triggered] Scheduled morning digest triggered
  Context: {"period": "morning", "digest_id": "abc-123"}
```

**Components logged:**
- `scheduler` - Schedule triggers, updates, skips
- `pipeline` - Digest generation stages and completion
- `feeds` - Feed fetch results (total/new articles, timing)
- `articles` - Extraction and summarization results
- `epub` - EPUB generation
- `maintenance` - Daily cleanup tasks

**Accessing logs on Docker:**
```bash
# View recent logs
docker exec -it ghostwriter tail -100 /app/logs/ghostwriter.log

# Copy logs to host
docker cp ghostwriter:/app/logs/. ./ghostwriter-logs/

# On Synology, logs volume is at:
# /path/to/ghostwriter_logs/
```

**Using logs for debugging:**
When investigating issues, the logs show:
1. Whether scheduled digests triggered
2. Which feeds were fetched and article counts
3. Which articles failed extraction or summarization
4. EPUB generation success and file size
5. Pipeline duration and any errors with stack traces

### Ghostwriter Frontend (Web UI)

The `ghostwriter/frontend/` directory contains a SvelteKit web dashboard for managing the Ghostwriter backend.

**Tech Stack:**
- **Framework:** SvelteKit 2.x (Svelte 5) with TypeScript
- **Build:** Vite, static adapter (SPA mode)
- **Styling:** Tailwind CSS + Bits UI (headless components) + Lucide icons
- **State:** TanStack SvelteQuery
- **Notifications:** Svelte Sonner

**Development:**
```bash
cd ghostwriter/frontend
npm install
npm run dev              # Dev server with HMR
npm run build            # Production build to ./build/
npm run check            # TypeScript & Svelte type checking
```

**Pages:**
- `/` - Dashboard (health, feed count, recent digests, quick actions, processing progress)
- `/feeds` - Feed CRUD (search, mode selection, active/paused toggle)
- `/digests` - Digest history (filter by status/period, download EPUB, view articles)
- `/settings` - Schedules, API tokens, Wallabag config, newsletter OAuth, activity logs
- `/newsletters` - Newsletter integration setup

**Key Files:**
- API client: `src/lib/api/client.ts`
- Type definitions: `src/lib/api/types.ts`
- UI components: `src/lib/components/ui/`

## Epilogue iOS App

The `EpilogueIOS/` directory contains an iOS client built with SwiftUI.

**Tech Stack:**
- **Language:** Swift / SwiftUI
- **Min iOS:** 18.0
- **Build System:** Tuist 4.x (modular project generation)
- **Persistence:** SwiftData
- **Architecture:** MVVM + Clean Architecture (6 modules)

**Key Libraries:**
- `FeedKit` - RSS/Atom parsing
- `SwiftSoup` - HTML parsing and extraction
- `ZIPFoundation` - EPUB generation
- `EpilogueShared` - KMP shared Ghostwriter client (XCFramework)

**Module Structure:**
```
EpilogueIOS/
├── App/                          # Main app target
│   ├── Sources/
│   │   ├── EpilogueApp.swift     # Entry point, DI setup
│   │   ├── Services/             # Ghostwriter sync, background tasks, heartbeat
│   │   └── Views/                # SwiftUI views (FeedList, Settings, History, Reader)
├── Modules/
│   ├── Domain/                   # Models (Feed, Digest, DigestArticle), protocols
│   ├── Data/                     # Repositories, persistence (SwiftData), services
│   ├── ContentProcessing/        # FeedKit + SwiftSoup pipeline
│   ├── AIServices/               # OpenAI (GPT-4o-mini) summarization
│   ├── EPUBGeneration/           # EPUB 3.0 builder with e-ink CSS
│   └── GhostwriterClient/       # Server sync client (delegates to shared KMP client)
└── Tuist/
    └── Package.swift             # SPM dependencies
```

**Build (requires Tuist):**

The iOS build depends on the shared KMP XCFramework. Build it first if it doesn't exist:
```bash
# From repo root — build the XCFramework
./gradlew :shared:assembleEpilogueSharedDebugXCFramework

# Then generate and build the iOS project
cd EpilogueIOS
tuist generate                    # Generate Xcode project
tuist build                       # Build via CLI
```

The `GhostwriterClient` module references the XCFramework at `shared/build/XCFrameworks/debug/EpilogueShared.xcframework`. This path is configured in `EpilogueIOS/Modules/GhostwriterClient/Project.swift`.

**Key Patterns:**
- SwiftData `@Model` classes for Feed, Digest, DigestArticle
- Background tasks via `BGTaskScheduler` for digest generation and Ghostwriter sync
- `GhostwriterSyncCoordinator` orchestrates feed/digest/config sync with server
- `GhostwriterClient` uses `#if canImport(EpilogueShared)` to route through shared KMP client when available
- Keychain storage for API keys
