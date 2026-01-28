# Epilogue

A cross-platform app that creates daily EPUB digests from your RSS feeds, optimized for e-ink devices.

## Overview

Epilogue aggregates content from RSS/Atom feeds, processes articles through either full extraction or AI summarization, and compiles them into a clean EPUB file for offline reading. Think of it as your personal "daily newspaper" generator.

**Target Devices:** Onyx Boox Palma 2 (Android), iPhone (iOS)

## Features

- **RSS/Atom Feed Support** - Add unlimited feeds with custom nicknames
- **Two Processing Modes:**
  - **Fidelity** - Full article extraction with ads/sidebars removed
  - **Briefing** - AI-powered summaries using OpenAI API
- **Daily EPUB Generation** - Scheduled background generation (morning, noon, evening)
- **E-ink Optimized UI** - High contrast, monochrome tint, serif typography, no animations
- **Digest History** - Browse and re-read past digests
- **Ghostwriter Server** - Optional self-hosted server for centralized digest generation
- **Cross-device Sync** - Sync feeds, config, and digests via Ghostwriter

## Screenshots

*Coming soon*

---

## iOS App

### Requirements

- iOS 18.0+
- Xcode 26+
- [Tuist](https://tuist.io) for project generation
- OpenAI API key (for Briefing mode only)

### Building

```bash
cd EpilogueIOS

# Install dependencies and generate Xcode project
tuist install
tuist generate

# Build from command line
xcodebuild -workspace Epilogue.xcworkspace -scheme Epilogue build
```

### Tech Stack

- **Language:** Swift 5.9
- **UI:** SwiftUI
- **Architecture:** Clean Architecture with modular Tuist workspace
- **Persistence:** SwiftData
- **Secrets:** Keychain (via custom wrapper)
- **RSS Parsing:** [FeedKit](https://github.com/nmdias/FeedKit)
- **Content Extraction:** [SwiftSoup](https://github.com/scinfu/SwiftSoup) (HTML parsing + readability)
- **EPUB Generation:** Custom builder with [ZIPFoundation](https://github.com/weichsel/ZIPFoundation)
- **AI Summarization:** OpenAI API (direct integration)
- **Background Tasks:** BGProcessingTask for scheduled digest generation
- **Text Rendering:** CoreText pagination with NSAttributedString

### Project Structure

```
EpilogueIOS/
├── App/                          # Main iOS app target
│   └── Sources/
│       ├── EpilogueApp.swift     # App entry point & dependency wiring
│       ├── ContentView.swift     # Tab-based navigation
│       ├── Views/
│       │   ├── FeedListView      # Feed management (add/edit/delete)
│       │   ├── HistoryView       # Digest history with swipe actions
│       │   ├── DigestDetailView  # Digest → e-ink reader
│       │   ├── EinkReaderView    # Paginated e-ink reader (CoreText)
│       │   ├── SettingsView      # Schedule, API key, generation
│       │   └── GhostwriterSettingsView
│       └── Services/
│           ├── LocalDigestService     # On-device digest generation
│           ├── LocalDigestScheduler   # BGProcessingTask scheduling
│           └── GhostwriterSync*       # Server sync coordinator
├── Modules/
│   ├── Domain/                   # Models, protocols (zero dependencies)
│   ├── Data/                     # Repositories, SwiftData, generators
│   ├── ContentProcessing/        # FeedParser, ContentExtractor
│   ├── EPUBGeneration/           # EPUB builder (ZIPFoundation)
│   ├── AIServices/               # OpenAI summarization service
│   └── GhostwriterClient/       # Server API client
└── Tuist/
    ├── ProjectDescriptionHelpers/
    └── Package.swift             # External dependencies
```

### E-ink Reader

The built-in reader is designed for e-ink-like reading on any device:

- **CoreText pagination** - Articles split across pages using precise text measurement
- **Serif typography** - Georgia font family with proper bold/italic support
- **Tap/swipe navigation** - Left/right tap zones and swipe gestures
- **Markdown rendering** - Converts `**bold**`, `*italic*`, and `## headings` from AI output
- **Monochrome UI** - Black tint throughout, no system blue
- **Table of contents** - Jump to any article instantly

---

## Android App

### Requirements

- Android 13+ (API 33)
- OpenAI API key (for Briefing mode only)

### Building

```bash
# Build debug APK
./gradlew assembleDebug

# Build release APK
./gradlew assembleRelease

# Run tests
./gradlew test
```

### Tech Stack

- **Language:** Kotlin
- **UI:** Jetpack Compose with Material 3
- **Architecture:** MVVM with Clean Architecture
- **DI:** Hilt
- **Database:** Room
- **Networking:** Retrofit + OkHttp
- **Background:** WorkManager
- **RSS Parsing:** [RSS-Parser](https://github.com/prof18/RSS-Parser)
- **Article Extraction:** [Readability4J](https://github.com/dankito/Readability4J)
- **EPUB Generation:** [epub4j](https://github.com/documentnode/epub4j)

### Project Structure

```
app/
├── data/
│   ├── local/          # Room database entities and DAOs
│   ├── remote/         # Retrofit services, OpenAI API
│   └── repository/     # Data repositories
├── domain/
│   └── model/          # Domain models (Feed, ProcessedArticle, etc.)
├── di/                 # Hilt dependency injection modules
├── service/
│   ├── ContentProcessor    # Article extraction pipeline
│   ├── EpubGenerator       # EPUB file creation
│   ├── OpenAIService       # AI summarization
│   └── DailyDigestWorker   # Background job scheduler
└── ui/
    ├── feed/           # Feed management screens
    ├── history/        # Digest history browser
    └── settings/       # App configuration
```

---

## Ghostwriter Server

An optional Python server that handles digest generation centrally, useful when running on a NAS or home server.

- **Scheduled generation** - Configurable morning/noon/evening schedules
- **AI processing** - OpenAI, Gemini, or local Ollama
- **REST API** - Full feed, digest, and config management
- **Docker deployment** - Single container with docker-compose

See [`ghostwriter/README.md`](ghostwriter/README.md) for setup instructions.

## EPUB Output

Generated files use the naming convention `Epilogue_YYYY-MM-DD.epub` (local) or `YYYY-MM-DD_period.epub` (Ghostwriter).

The EPUB structure:
- **Cover Page** - Title and date
- **The Briefing** - AI summaries (if any feeds use Briefing mode)
- **Deep Dives** - Full articles (Fidelity mode)

## License

*TBD*

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
