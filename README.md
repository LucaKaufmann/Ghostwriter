# Epilogue

An Android app that creates a daily EPUB digest from your RSS feeds, optimized for e-ink devices.

## Overview

Epilogue aggregates content from RSS/Atom feeds, processes articles through either full extraction or AI summarization, and compiles them into a clean EPUB file for offline reading. Think of it as your personal "daily newspaper" generator.

**Target Device:** Onyx Boox Palma 2 (and other Android 13+ e-ink devices)

## Features

- **RSS/Atom Feed Support** - Add unlimited feeds with custom nicknames
- **Two Processing Modes:**
  - **Fidelity** - Full article extraction with ads/sidebars removed (via Readability4J)
  - **Briefing** - AI-powered summaries using OpenAI API
- **Daily EPUB Generation** - Scheduled background generation via WorkManager
- **E-ink Optimized UI** - High contrast, no animations, minimal design
- **Digest History** - Browse and re-read past digests

## Screenshots

*Coming soon*

## Requirements

- Android 13+ (API 33)
- OpenAI API key (for Briefing mode only)

## Building

```bash
# Clone the repository
git clone git@github.com:LucaKaufmann/Epilogue.git
cd Epilogue

# Build debug APK
./gradlew assembleDebug

# Build release APK
./gradlew assembleRelease

# Run tests
./gradlew test
```

## Tech Stack

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

## Project Structure

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

## Configuration

### OpenAI API Key
1. Open Settings in the app
2. Enter your OpenAI API key
3. The key is stored securely using EncryptedSharedPreferences

### Schedule Time
Set your preferred daily digest generation time in Settings (default: 10:00 PM).

## EPUB Output

Generated files are saved to `/Documents/Epilogue/` with the naming convention `Epilogue_YYYY-MM-DD.epub`.

The EPUB structure:
- **Cover Page** - Title and date
- **The Briefing** - AI summaries (if any feeds use Briefing mode)
- **Deep Dives** - Full articles (Fidelity mode)

## License

*TBD*

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
