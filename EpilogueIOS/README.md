# Epilogue iOS

A modular iOS application for aggregating RSS/Atom feeds and generating daily EPUB digests optimized for e-ink devices.

## Overview

Epilogue iOS fetches articles from your favorite RSS feeds, processes them using AI summarization or full content extraction, and compiles them into beautifully formatted EPUB files perfect for reading on e-ink devices like the Onyx Boox Palma 2.

## Features

- **RSS/Atom Feed Management**: Add and manage multiple feeds with custom processing modes
- **Dual Processing Modes**:
  - **Briefing**: AI-powered summaries using GPT-4o-mini
  - **Deep Dive**: Full article extraction with content filtering
- **Scheduled Generation**: Automatic daily digest creation via background tasks
- **Manual Trigger**: Generate digests on demand with "Run Now"
- **E-ink Optimized**: High contrast, serif fonts, optimized layout for e-ink displays
- **30-Digest Retention**: Automatic cleanup of old digests
- **Notifications**: Optional completion notifications

## Requirements

- iOS 18.0+
- Xcode 17+
- Tuist 4.x
- OpenAI API key (for Briefing mode)

## Project Structure

The app uses Tuist for modular architecture:

```
EpilogueIOS/
├── App/                    # Main iOS app target
├── Modules/
│   ├── Domain/            # Core models and protocols
│   ├── Data/              # SwiftData repositories and services
│   ├── ContentProcessing/ # RSS parsing and content extraction
│   ├── AIServices/        # OpenAI integration
│   └── EPUBGeneration/    # EPUB file creation
└── Tuist/                 # Tuist configuration and dependencies
```

## Setup

### 1. Install Tuist

```bash
curl -Ls https://install.tuist.io | bash
```

### 2. Install Dependencies

```bash
cd EpilogueIOS
tuist install
```

### 3. Generate Xcode Project

```bash
tuist generate
```

### 4. Open in Xcode

```bash
xed .
```

## Architecture

### Domain Layer
- `Feed`: RSS feed configuration
- `Digest`: Generated EPUB metadata
- `DigestArticle`: Processed article storage
- `ProcessedArticle`: Transient processing model
- Repository protocols for all data operations

### Data Layer
- **SwiftData**: Local persistence for feeds and digests
- **Keychain**: Secure API key storage
- **Repositories**: Implementation of domain protocols
  - `FeedRepository`: Feed CRUD operations
  - `DigestRepository`: Digest management with retention policy
  - `SettingsRepository`: User preferences and API keys
  - `ArticleRepository`: Article fetching and processing orchestration

### Content Processing
- **FeedParser**: RSS/Atom/JSON feed parsing using FeedKit
- **ContentExtractor**: HTML extraction and cleaning with SwiftSoup
- **OpenAIService**: AI summarization with GPT-4o-mini

### EPUB Generation
- **EPUBBuilder**: Complete EPUB 3.0 file creation
- **E-ink CSS**: Optimized stylesheet for e-ink displays
- **DigestGenerator**: End-to-end digest creation orchestration

### Background Processing
- **DigestScheduler**: BGTaskScheduler integration
- **Automatic Scheduling**: Daily digest generation at configured time
- **Notifications**: Completion alerts with article counts

## Usage

### Adding a Feed

1. Tap the "Feeds" tab
2. Tap the "+" button
3. Enter feed URL and name
4. Select processing mode (Briefing or Deep Dive)
5. Set max articles per digest
6. Tap "Add"

### Configuring Settings

1. Tap the "Settings" tab
2. Enter your OpenAI API key (required for Briefing mode)
3. Enable scheduled digests and set generation time
4. Adjust minimum word count filter
5. Toggle completion notifications

### Generating a Digest

**Automatic (Scheduled)**:
- Enable "Scheduled Digests" in Settings
- Choose your preferred generation time
- Digests generate automatically daily

**Manual (Run Now)**:
- Go to Settings
- Tap "Generate Digest Now"
- Wait for completion notification

### Viewing Digests

1. Tap the "History" tab
2. View all generated digests
3. See article counts and generation status
4. Access EPUB files in Files app: Documents/Epilogue/

## Dependencies

- **FeedKit**: RSS/Atom parsing
- **SwiftSoup**: HTML parsing and extraction
- **ZIPFoundation**: EPUB file creation
- **SwiftData**: Local persistence
- **BGTaskScheduler**: Background task scheduling
- **UserNotifications**: Completion alerts

## Testing

```bash
# Run all tests
tuist test

# Run specific module tests
xcodebuild test -workspace Epilogue.xcworkspace -scheme Domain
xcodebuild test -workspace Epilogue.xcworkspace -scheme Data
```

## Build

```bash
# Debug build
tuist build

# Release build
tuist build --configuration Release
```

## Technical Details

### SwiftData Schema
- Models use `@Model` macro for SwiftData persistence
- Relationships: Digest → [DigestArticle] (cascade delete)
- Unique constraints on Feed.url and Digest.id

### Background Tasks
- Task ID: `com.epilogue.app.digestgeneration`
- Requires network connectivity
- No external power requirement
- Registered in Info.plist

### EPUB Structure
- EPUB 3.0 compliant
- Cover page with date
- Table of contents
- Separate sections for Briefings and Deep Dives
- E-ink optimized CSS

### File Storage
- Location: `Documents/Epilogue/`
- Format: `Epilogue_YYYY-MM-DD.epub`
- Automatic cleanup via retention policy

## Known Issues

- Keychain tests fail in iOS Simulator (error -34018) - Expected behavior, works on device
- Background tasks require device testing for full functionality

## Contributing

The iOS app shares the same architectural principles as the Android version while leveraging iOS-specific frameworks and patterns.

## License

Copyright © 2026 Epilogue. All rights reserved.
