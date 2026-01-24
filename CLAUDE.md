# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Epilogue is an Android application that aggregates RSS/Atom feeds, processes content through either full extraction or AI summarization, and compiles results into daily EPUB files for offline reading on e-ink devices (optimized for Onyx Boox Palma 2).

## Build Commands

**Important:** Set JAVA_HOME to Android Studio's bundled JDK before running Gradle:
```bash
export JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home"
```

```bash
./gradlew build              # Build the project
./gradlew assembleDebug      # Build debug APK
./gradlew assembleRelease    # Build release APK
./gradlew test               # Run unit tests
./gradlew connectedAndroidTest  # Run instrumented tests
./gradlew lint               # Run lint checks
./gradlew clean              # Clean build artifacts
```

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

- **Language:** Kotlin
- **Min SDK:** Android 13+
- **UI:** Jetpack Compose with Material 3
- **Architecture:** MVVM with Clean Architecture
- **DI:** Hilt
- **Async:** Coroutines & Flow
- **Database:** Room
- **Background:** WorkManager

### Key Libraries
- `Retrofit` + `OkHttp` (60s timeouts for slow scraping)
- `Readability4J` (net.dankito.readability4j) for article extraction
- `Jsoup` for HTML parsing
- `RSS-Parser` (com.prof18.rssparser) for feed parsing
- `Epublib` (nl.siegmann.epublib) for EPUB generation

## Architecture

```
app/
├── data/
│   ├── local/          # Room entities, DAOs
│   ├── remote/         # Retrofit services, OpenAI API
│   └── repository/     # ArticleRepository
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

After updating the codebase, run migrations before deploying:
```bash
cd ghostwriter
python scripts/migrate_add_article_content.py
```

On Docker, exec into the container:
```bash
docker exec -it ghostwriter python scripts/migrate_add_article_content.py
```

### API Endpoints

- `GET /health` - Health check
- `GET /feeds` - List feeds
- `POST /feeds/sync` - Sync feeds from app
- `POST /digests/trigger` - Trigger digest generation
- `GET /digests` - List digests
- `GET /digests/{id}/articles` - Get articles with content
- `GET /digests/{filename}` - Download EPUB

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
