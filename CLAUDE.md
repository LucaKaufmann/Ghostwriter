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
