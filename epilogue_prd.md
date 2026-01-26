# Software Development Specification: Epilogue

**Version:** 2.0 (Current Implementation)
**Project Name:** Epilogue
**Target Platform:** Android 13+ (Optimized for E-ink / Onyx Boox Palma 2)
**Language:** Kotlin
**Architecture:** MVVM with Clean Architecture principles
**Last Updated:** January 2026

---

## 1. Product Overview

**Epilogue** is an Android application that serves as a personal "closing ceremony" for the information diet. It aggregates content from RSS feeds, blogs, and social media bridges, filters it through a user-defined processing engine (AI summary or Direct Compilation), and compiles it into a clean, distraction-free EPUB file on a daily schedule.

**Core Value:** Automates the creation of a personalized "daily newspaper" for offline reading, specifically tailored to the constraints and strengths of e-ink devices.

---

## 2. Functional Requirements

### 2.1 Content Aggregation (Input)

* **RSS/Atom Support:** The app must accept standard RSS and Atom feed URLs.
* **Feed Management:** Users can Add, Edit, and Delete feeds via dedicated UI screens.
* **Feed Metadata:** Each feed object must contain:
  * `URL`: The source address (primary key).
  * `Name`: User-defined label (e.g., "Hacker News").
  * `Processing Mode`: Enum (`FIDELITY` or `BRIEFING`).
  * `Last Fetched`: Unix timestamp for incremental updates.
  * `Max Articles`: Optional limit on number of articles to fetch per feed (default: unlimited).
* **Reactive Updates:** Feed list uses Flow for automatic UI updates when feeds are added/modified/deleted.



### 2.2 Content Processing (The Pipeline)

The app implements a sophisticated multi-stage content processing pipeline with intelligent fetching and fallback strategies.

#### 2.2.1 Smart Content Analysis

Before fetching full articles from URLs, the app analyzes RSS feed content to determine if full article is already available:

* **ContentAnalyzer:** Evaluates RSS content and returns:
  * `ContentType`: FULL_ARTICLE, PREVIEW, or UNCERTAIN
  * `wordCount`: Word count of RSS content
  * `hasReadMoreLink`: Detection of "read more" patterns in 6+ languages (English, German, French, Spanish, Italian, Portuguese)
  * `isTruncated`: Detects ellipsis, en-dash endings, incomplete sentences
  * `confidence`: Score for content type determination

* **Smart Fetching Strategy:**
  * **FULL_ARTICLE** → Use RSS content directly (saves bandwidth)
  * **PREVIEW** → Fetch full article from original URL
  * **UNCERTAIN** → Try RSS first; fetch from URL if content < 150 words

* **RSS Content Cleaning:**
  * Remove "read more" links (multilingual patterns)
  * Strip tracking pixels and analytics
  * Remove style/class attributes
  * Filter out ads and tracking elements

#### 2.2.2 Processing Modes

The app supports two distinct processing modes per feed:

* **Mode A: Fidelity (Direct Compilation)**
  * **Goal:** Deep reading of long-form content.
  * **Logic:** Smart fetch → Extract Full Content (using `Readability4J` if needed) → Clean HTML.
  * **Output:** Full article text with original structure (headers, bolding, images) preserved. Sidebar/Ads removed.
  * **Filtering:** Configurable minimum word count threshold (global setting, default: 0).
  * **Fallback:** If Readability4J fails, wraps text content in `<p>` tags.

* **Mode B: Briefing (AI Summarization)**
  * **Goal:** Rapid catch-up on high-volume news.
  * **Logic:** Smart fetch → Strip HTML → Truncate to 4000 chars (word-boundary aware) → Send to OpenAI API → Convert Markdown to HTML.
  * **LLM Integration:**
    * Uses OpenAI `gpt-4o-mini` model
    * User must supply their own API Key (stored encrypted in `EncryptedSharedPreferences`)
    * System Prompt enforces "neutral editor" tone suitable for bedtime reading
    * Target: <150 words, calm language, no sensationalism
  * **Output:** A structured summary (Hook, Key Details, Significance) in Markdown format.
  * **Markdown to HTML Conversion:**
    * `**text**` → `<strong>text</strong>`
    * `*text*` → `<em>text</em>`
    * `- item` → `<li>item</li>` (wrapped in `<ul>`)
    * Double newlines → paragraph breaks
  * **Fallback:** If OpenAI API fails, returns full article with `isSummary=false` flag.

#### 2.2.3 Processing Pipeline Features

* **Parallel Processing:** All feeds fetched concurrently using coroutineScope with async/awaitAll
* **Per-Feed Limits:** Respects `maxArticles` setting per feed
* **Incremental Updates:** Uses `lastFetched` timestamp to fetch only new articles when triggered by scheduled digest
* **Manual Override:** "Run Now" can fetch all articles regardless of `lastFetched`
* **Article Sorting:** Summaries first, then full articles
* **Timeout Handling:** 60-second timeout for URL fetches



### 2.3 EPUB Generation (Output)

* **File Format:** Standard `.epub` file with embedded stylesheet.
* **Naming Convention:** `Epilogue_YYYY-MM-DD.epub`
* **Structure:**
  * **Cover Page:** Title ("Epilogue") + Date + Tagline
  * **Stylesheet:** E-ink optimized CSS
    * Pure black (#000000) on white (#FFFFFF)
    * Serif font with 1.6 line-height
    * No gradients or animations
    * Justified text for body content
    * h1 with 2px bottom border
    * Blockquotes with left border
    * Monospace code blocks
  * **Section 1: The Briefing:** All AI summaries compiled into one continuous chapter
    * Each article includes: title, byline, content, original URL link
    * Articles separated by horizontal rules
  * **Section 2: Deep Dives:** Full-text articles as separate chapters with TOC navigation
    * Each chapter: h1 title, byline, full HTML content, source link
    * Chapter-level TOC entries

* **Storage:** Save files to `/Documents/Epilogue/` (external storage, public directory).
* **File Viewing:** Integration with external EPUB readers via FileProvider for secure file sharing.

### 2.4 Digest History & Management

* **Digest Entity:** Each generated EPUB is recorded in the database with metadata:
  * `id`: Auto-generated primary key
  * `generatedAt`: Unix timestamp
  * `epubFilePath`: Absolute path to saved EPUB
  * `articleCount`: Total number of articles in digest
  * `briefingCount`: Number of AI summaries
  * `fidelityCount`: Number of full articles
  * `triggerType`: SCHEDULED or MANUAL
  * `feedNames`: Comma-separated list of source feeds

* **DigestArticle Entity:** Articles within each digest are persisted:
  * `id`: Auto-generated primary key
  * `digestId`: Foreign key to parent digest (cascade delete)
  * `title`, `author`, `content`, `originalUrl`: Article data
  * `isSummary`: Boolean flag
  * `sortOrder`: Maintains article order within digest

* **Retention Policy:** Maximum 30 digests retained. When creating digest #31, oldest digest is automatically deleted along with:
  * Associated `DigestArticle` records (cascade delete)
  * Physical EPUB file from storage

* **History UI:**
  * Displays list of past digests sorted by most recent first
  * Shows: date, article count, briefing/fidelity split, trigger type
  * Actions: View EPUB in external reader, Delete digest (with confirmation)
  * Error handling for missing EPUB files

### 2.5 Automation & System Integration

#### 2.5.1 Background Execution (DailyDigestWorker)

* **Implementation:** `CoroutineWorker` using Jetpack WorkManager
* **Work Type:** 24-hour PeriodicWorkRequest with UPDATE policy
* **Constraints:**
  * `NetworkType.CONNECTED`: Requires active internet connection
  * `RequiresBatteryNotLow`: Only runs when battery not low

* **Input Parameters:**
  * `KEY_FETCH_ALL`: Boolean - if true, fetch all articles; if false, fetch only new articles since `lastFetched`
  * `KEY_IS_MANUAL`: Boolean - marks trigger type as MANUAL or SCHEDULED

* **Workflow:**
  1. Retrieve all feeds from FeedRepository
  2. Fetch articles via ArticleRepository.fetchFromAllFeeds()
  3. Generate EPUB file via EpubGenerator
  4. Save digest metadata to DigestRepository with:
     * Article counts (total, briefing, fidelity)
     * Feed names list
     * Trigger type
     * File path
  5. Trigger MediaScannerConnection
  6. Cleanup old digests if count exceeds 30

* **Error Handling:** Returns Result.failure() with exception message on any step failure

#### 2.5.2 Scheduling (DigestScheduler)

* **User-Configurable Time:** Users set preferred execution time (hour + minute) in Settings
* **Schedule Calculation:**
  * Calculates time until next scheduled run
  * If scheduled time has passed today, schedules for tomorrow
  * Initial delay passed to PeriodicWorkRequest

* **Unique Work:** Uses `enqueueUniquePeriodicWork()` with UPDATE policy to replace existing schedule when time changes

* **Manual Trigger:**
  * "Run Now" button in Settings
  * Uses OneTimeWorkRequest with REPLACE policy
  * Fetches only new articles by default (`fetchAll=false`)
  * Marks trigger type as MANUAL

* **Status Monitoring:**
  * LiveData<WorkInfo> for periodic work status
  * LiveData<WorkInfo> for immediate/manual work status
  * UI can observe work progress and completion

* **Application Startup:**
  * `EpilogueApplication.onCreate()` initializes DigestScheduler
  * Ensures scheduling persists across app updates and device reboots

#### 2.5.3 Media Scanner Integration

* **Purpose:** Makes EPUB files immediately visible in Boox Library widget and other document apps
* **Implementation:** `MediaScannerConnection.scanFile()` triggered after each EPUB save
* **Critical:** Without this, files only appear after device reboot on Boox devices

### 2.6 Configuration & Settings Management

#### 2.6.1 SettingsRepository

* **Dual Storage Strategy:**
  * **Encrypted Storage:** `EncryptedSharedPreferences` (AES256-GCM) for sensitive data
    * OpenAI API key
  * **Standard Storage:** Regular SharedPreferences for non-sensitive settings
    * Schedule time (hour, minute)
    * Minimum word count filter

* **Default Values:**
  * Schedule time: 22:00 (10 PM)
  * Minimum word count: 0 (no filtering)
  * API key: empty string

* **Reactive Updates:**
  * `apiKeyFlow`: StateFlow<String> for reactive API key availability
  * Settings changes automatically trigger dependent actions (e.g., schedule time change triggers WorkManager reschedule)

#### 2.6.2 Settings UI

* **Configuration Options:**
  * **OpenAI API Key Input:**
    * Secure text field with visibility toggle
    * Two-phase save: update UI state, then persist encrypted
    * Success feedback via `apiKeySaved` flag
    * Required for BRIEFING mode functionality

  * **Schedule Time Picker:**
    * Hour and minute selection (24-hour format)
    * Automatic rescheduling on time change via DigestScheduler
    * Default: 22:00

  * **Minimum Word Count:**
    * Integer input field
    * Filters out articles below threshold
    * Applies to both FIDELITY and BRIEFING modes
    * Default: 0 (disabled)

  * **Manual Digest Trigger:**
    * "Run Now" button
    * Triggers immediate OneTimeWorkRequest
    * Success feedback via `digestTriggered` flag
    * Fetches only new articles (respects `lastFetched`)

#### 2.6.3 Feed Configuration UI

* **Feed Management:**
  * Add feed dialog: URL, name, processing mode, max articles
  * Edit feed dialog: modify any feed parameter
  * Delete feed: confirmation required
  * Feed list: displays all configured feeds with mode indicators

* **Per-Feed Settings:**
  * Processing mode toggle (FIDELITY/BRIEFING)
  * Max articles limit (optional, integer input)
  * Last fetched timestamp (display only)

---

## 3. Technical Decisions & Stack

### 3.1 Core Stack

* **Language:** Kotlin.
* **UI Framework:** Jetpack Compose (Material 3).
* **Asynchronous:** Coroutines & Flow.
* **Dependency Injection:** Hilt.

### 3.2 Key Libraries

* **Networking:** `Retrofit` + `OkHttp` (Timeouts set to 60s to handle slow article scraping).
* **HTML Parsing:** `Readability4J` (net.dankito.readability4j) + `Jsoup`.
* **RSS Parsing:** `RSS-Parser` (com.prof18.rssparser).
* **EPUB Creation:** `Epublib` (nl.siegmann.epublib).
* **Database:** `Room` (SQLite).
* **Background:** `Jetpack WorkManager`.

### 3.3 Architecture Layers

The app follows Clean Architecture principles with clear separation of concerns:

```
app/src/main/java/com/example/epilogue/
├── data/                       # Data Layer
│   ├── local/                  # Room database (DAOs, entities)
│   │   ├── FeedDao
│   │   ├── DigestDao
│   │   └── EpilogueDatabase (version 3)
│   ├── remote/openai/          # API clients
│   │   ├── OpenAIApi (Retrofit interface)
│   │   └── OpenAIService (business logic)
│   └── repository/             # Repository implementations
│       ├── FeedRepository      # Feed CRUD + Flow updates
│       ├── DigestRepository    # Digest persistence + cleanup
│       ├── ArticleRepository   # Core orchestration + processing
│       └── SettingsRepository  # Encrypted preferences
├── domain/model/               # Domain Layer (pure Kotlin)
│   ├── Feed
│   ├── Digest
│   ├── DigestArticle
│   ├── ProcessedArticle
│   ├── ProcessingMode (enum)
│   ├── TriggerType (enum)
│   └── ContentType (enum)
├── service/                    # Business Logic Services
│   ├── ContentProcessor        # Smart fetching + cleaning
│   ├── ContentAnalyzer         # RSS content analysis
│   ├── EpubGenerator           # EPUB creation + styling
│   ├── DigestScheduler         # WorkManager orchestration
│   └── DailyDigestWorker       # Background processing
├── di/                         # Dependency Injection (Hilt)
│   ├── DatabaseModule
│   ├── NetworkModule
│   └── OpenAIModule
├── ui/                         # Presentation Layer
│   ├── feed/                   # Feed management screens
│   │   ├── FeedScreen
│   │   └── FeedViewModel
│   ├── settings/               # Configuration screens
│   │   ├── SettingsScreen
│   │   └── SettingsViewModel
│   ├── history/                # Digest history screens
│   │   ├── HistoryScreen
│   │   └── HistoryViewModel
│   └── navigation/             # Compose navigation
└── EpilogueApplication.kt      # App initialization
```

**Key Architectural Patterns:**
* **Repository Pattern:** All data access through repositories (4 repositories)
* **MVVM:** ViewModels manage UI state, expose StateFlow/LiveData
* **Dependency Injection:** Hilt provides singletons and scoped dependencies
* **Flow/StateFlow:** Reactive data streams for UI updates
* **Clean Architecture:** Domain models independent of frameworks
* **Use Case Pattern:** Complex operations encapsulated in service classes

### 3.4 Repository Layer Details

#### FeedRepository
* Wraps FeedDao for database operations
* Provides Flow<List<Feed>> for reactive UI updates
* Updates `lastFetched` timestamp after successful fetches
* Singleton via Hilt @Singleton annotation

#### DigestRepository
* Manages digest persistence and cleanup
* **Retention Policy:** Enforces 30-digest maximum
  * On insert: checks count, deletes oldest if exceeds 30
  * Cascade deletes DigestArticle records
  * Deletes physical EPUB file from storage
* Saves digest + articles in Room transaction
* Provides Flow<List<Digest>> for history UI
* Query methods for digest metadata and articles

#### ArticleRepository
* **Core orchestration** for content processing pipeline
* Key responsibilities:
  * Parallel fetching from multiple feeds (async/awaitAll)
  * Smart content analysis via ContentAnalyzer
  * Conditional URL fetching based on ContentType
  * Processing mode application (FIDELITY/BRIEFING)
  * OpenAI API integration with fallback
  * Per-feed maxArticles limiting
  * Incremental vs full fetch logic
  * Article sorting (summaries first)
* Dependencies: RSS-Parser, ContentProcessor, OpenAIService, FeedRepository

#### SettingsRepository
* **Dual storage** for encrypted and plain preferences
* Methods:
  * `getOpenAIApiKey()` / `setOpenAIApiKey()` - encrypted
  * `getScheduleTime()` / `setScheduleTime()` - triggers reschedule
  * `getMinWordCount()` / `setMinWordCount()`
  * `apiKeyFlow`: StateFlow<String> for reactive updates
* Uses EncryptedSharedPreferences (AES256-GCM) for API key
* Singleton via Hilt

### 3.5 UI/UX Constraints (E-Ink Optimization)

* **Theme:** High Contrast Mode. Pure Black (#000000) text on Pure White (#FFFFFF) background.
* **Motion:** `windowAnimationScale` set to 0 locally or animations globally disabled in Compose.
* **Typography:** Use a high-legibility serif font (e.g., Merriweather) for preview screens.

### 3.6 Data Models

#### 3.4.1 Room Database Entities

**Database Version:** 3 (with migrations 1→2, 2→3)

**Entity: Feed**

```kotlin
@Entity(tableName = "feeds")
data class Feed(
    @PrimaryKey val url: String,
    val name: String,
    val mode: ProcessingMode, // Enum: FIDELITY, BRIEFING
    val lastFetched: Long = 0L,
    val maxArticles: Int? = null // Optional per-feed article limit
)
```

**Entity: Digest**

```kotlin
@Entity(tableName = "digests")
data class Digest(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val generatedAt: Long,
    val epubFilePath: String,
    val articleCount: Int,
    val briefingCount: Int,
    val fidelityCount: Int,
    val triggerType: TriggerType, // SCHEDULED or MANUAL
    val feedNames: String // Comma-separated feed names
)
```

**Entity: DigestArticle**

```kotlin
@Entity(
    tableName = "digest_articles",
    foreignKeys = [ForeignKey(
        entity = Digest::class,
        parentColumns = ["id"],
        childColumns = ["digestId"],
        onDelete = ForeignKey.CASCADE
    )]
)
data class DigestArticle(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val digestId: Long,
    val title: String,
    val author: String,
    val content: String, // HTML
    val originalUrl: String,
    val isSummary: Boolean,
    val sortOrder: Int
)
```

#### 3.4.2 Domain Models (Transient)

**Model: ProcessedArticle**

```kotlin
data class ProcessedArticle(
    val title: String,
    val author: String,
    val content: String, // HTML or Markdown
    val originalUrl: String,
    val isSummary: Boolean
)
```

#### 3.4.3 Enums

**ProcessingMode:**
```kotlin
enum class ProcessingMode {
    FIDELITY,   // Full article extraction
    BRIEFING    // AI summarization
}
```

**TriggerType:**
```kotlin
enum class TriggerType {
    SCHEDULED,  // Triggered by periodic WorkManager job
    MANUAL      // Triggered by user "Run Now" action
}
```

**ContentType (for Smart Fetching):**
```kotlin
enum class ContentType {
    FULL_ARTICLE,  // RSS contains complete article
    PREVIEW,       // RSS contains only preview/excerpt
    UNCERTAIN      // Cannot determine with confidence
}
```

### 3.7 Dependency Injection (Hilt Modules)

#### DatabaseModule
* **Provides:** EpilogueDatabase (singleton)
* **Provides:** FeedDao (from database)
* **Provides:** DigestDao (from database)
* **Migrations:** Configured for version 1→2 (digest tables), 2→3 (maxArticles column)

#### NetworkModule
* **Provides:** OkHttpClient (singleton)
  * 60-second timeouts (connect, read, write)
  * HttpLoggingInterceptor at BASIC level
  * Used by both RSS-Parser and ContentProcessor

#### OpenAIModule
* **Provides:** Retrofit instance for OpenAI API
  * Base URL: https://api.openai.com/
  * GsonConverterFactory
  * Reuses OkHttpClient from NetworkModule
* **Provides:** OpenAIApi interface
  * Endpoint: POST /v1/chat/completions

#### Repository Bindings
* FeedRepository, DigestRepository, ArticleRepository, SettingsRepository
* All provided as @Singleton scope
* Constructor injection for dependencies

---

## 4. Key Features & Enhancements (vs Original MVP Spec)

This section highlights major features implemented beyond the original MVP specification:

### 4.1 Smart Content Fetching System
* **ContentAnalyzer** for RSS content evaluation (not in MVP)
* Multilingual "read more" link detection (6+ languages)
* Truncation pattern recognition (ellipsis, en-dash, incomplete sentences)
* Bandwidth optimization by avoiding unnecessary URL fetches
* Confidence-based decision making (FULL_ARTICLE/PREVIEW/UNCERTAIN)

### 4.2 Digest History & Retention Management
* **Digest entity** for EPUB metadata persistence (not in MVP)
* **DigestArticle entity** for article history (not in MVP)
* Cascade delete relationships
* 30-digest retention policy with automatic cleanup
* History UI with sort, view, and delete capabilities
* Trigger type tracking (SCHEDULED vs MANUAL)
* Statistics: briefing/fidelity counts, feed source list

### 4.3 Enhanced Configuration System
* **Per-feed configuration:** maxArticles limit (not in MVP)
* **SettingsRepository:** with encrypted API key storage (MVP mentioned encryption but not repository pattern)
* **StateFlow for reactive updates:** API key availability (not in MVP)
* **Automatic rescheduling:** on schedule time change (not in MVP)
* **Manual trigger with parameters:** fetchAll flag (MVP had "Run Now" but not parameterization)

### 4.4 Advanced Error Handling & Fallbacks
* **OpenAI failure fallback:** returns full article instead of failing (not in MVP)
* **Readability4J failure fallback:** wraps text in paragraphs (not in MVP)
* **Empty feed handling:** graceful degradation (not in MVP)
* **File viewing integration:** FileProvider for secure EPUB sharing (not in MVP)

### 4.5 WorkManager Enhancements
* **Input data parameters:** fetchAll, isManual flags for flexible execution (not in MVP)
* **Work status monitoring:** LiveData for UI feedback (not in MVP)
* **Application startup scheduling:** ensures persistence across reboots (implied in MVP but not detailed)
* **Unique work policies:** UPDATE for schedule changes, REPLACE for manual triggers (not in MVP)

### 4.6 Markdown Processing
* **Markdown to HTML conversion** for AI summaries (not in MVP - MVP showed Markdown but didn't specify conversion)
* Preserves formatting: bold, italic, lists, paragraph breaks
* Ensures EPUB compatibility

### 4.7 EPUB Enhancements
* **Detailed CSS stylesheet** for e-ink optimization (MVP mentioned optimization but not specifics)
* Horizontal rule separators between articles
* Source links for each article
* Byline formatting with author attribution
* Chapter-level TOC structure for full articles

---

## 5. Implementation Status

**All phases complete.** The Android application is fully implemented with all MVP features plus enhancements detailed in Section 4.

### **Phase 1: Skeleton & Feed Management** ✅ COMPLETE

* Android project initialized with Compose, Hilt, Room
* Permissions: `INTERNET`, `READ_EXTERNAL_STORAGE`, `WRITE_EXTERNAL_STORAGE`
* Room database (version 3) with Feed, Digest, DigestArticle entities
* Feed management UI with add/edit/delete dialogs
* Feed validation using RSS-Parser
* Per-feed configuration: processing mode, max articles

### **Phase 2: The Fetch & Clean Pipeline** ✅ COMPLETE

* ArticleRepository with parallel fetching (async/awaitAll)
* ContentProcessor with smart fetching and Readability4J integration
* ContentAnalyzer for RSS content evaluation
* Incremental updates via `lastFetched` timestamp comparison
* Word count filtering with configurable minimum threshold
* Multilingual "read more" detection and cleaning

### **Phase 3: The EPUB Generator & AI** ✅ COMPLETE

* EpubGenerator with epublib integration
* E-ink optimized CSS stylesheet
* Two-section EPUB structure (Briefing + Deep Dives)
* OpenAI integration with gpt-4o-mini model
* Encrypted API key storage via EncryptedSharedPreferences
* Markdown to HTML conversion for AI summaries
* Fallback handling for API failures
* MediaScannerConnection integration

### **Phase 4: Automation & E-ink Polish** ✅ COMPLETE

* DailyDigestWorker implemented as CoroutineWorker
* 24-hour periodic scheduling with user-configurable time
* WorkManager constraints: NetworkType.CONNECTED, RequiresBatteryNotLow
* DigestScheduler for schedule management and manual triggers
* Application startup initialization
* Pure B&W UI theme throughout
* "Run Now" button in settings with status feedback
* Digest history UI with view/delete actions

### **Phase 5: Enhancements** ✅ COMPLETE

* Digest history with 30-digest retention policy
* Trigger type tracking (SCHEDULED/MANUAL)
* Statistics and metadata for each digest
* FileProvider integration for EPUB viewing
* StateFlow/LiveData for reactive UI updates
* Comprehensive error handling and fallback strategies
* Smart content analysis and bandwidth optimization

---

## 6. iOS Port Considerations

This section provides guidance for porting Epilogue to iOS while maintaining feature parity with the Android implementation.

### 6.1 Target Platform
* **Language:** Swift
* **UI Framework:** SwiftUI
* **Minimum Version:** iOS 15+ (for async/await support)
* **Target Devices:** iPhone, iPad (optimized for e-ink devices like Boox Tab Ultra C)
* **Future Consideration:** Apple Intelligence / Foundation Models integration

### 6.2 Architecture Recommendations

**Modular Design with Swift Package Manager:**

```
EpilogueApp/
├── Packages/
│   ├── Domain/                 # Pure Swift domain models
│   │   ├── Models/
│   │   │   ├── Feed.swift
│   │   │   ├── Digest.swift
│   │   │   ├── ProcessedArticle.swift
│   │   │   └── Enums.swift
│   │   └── Protocols/
│   │       ├── FeedRepositoryProtocol.swift
│   │       ├── DigestRepositoryProtocol.swift
│   │       └── AIServiceProtocol.swift
│   ├── Data/                   # Data layer implementations
│   │   ├── Repositories/
│   │   ├── Persistence/        # CoreData/SwiftData
│   │   └── Network/            # URLSession wrappers
│   ├── Services/               # Business logic
│   │   ├── ContentProcessor/
│   │   ├── EPUBGenerator/
│   │   ├── AIServices/         # Protocol-based AI integration
│   │   │   ├── AIServiceProtocol.swift
│   │   │   ├── OpenAIService.swift
│   │   │   ├── ClaudeService.swift (future)
│   │   │   └── AppleIntelligenceService.swift (future)
│   │   └── DigestScheduler/
│   └── UI/                     # SwiftUI views
│       ├── Feeds/
│       ├── Settings/
│       └── History/
```

**Key Architectural Patterns:**
* **Protocol-Oriented Programming:** Use protocols for all service interfaces (especially AI services)
* **Async/Await:** Replace Kotlin coroutines with Swift Concurrency
* **Combine or AsyncStream:** Replace Flow with Combine Publishers or AsyncSequence
* **Dependency Injection:** Use protocol-based DI (avoid singletons where possible)
* **SwiftData or CoreData:** Replace Room database

### 6.3 AI Service Protocol Design

To support multiple AI providers (OpenAI, Claude, Apple Intelligence), implement a protocol-based architecture:

```swift
// Core protocol for AI summarization
protocol AIServiceProtocol {
    func summarize(
        title: String,
        content: String,
        url: String
    ) async throws -> String

    var isAvailable: Bool { get }
    var providerName: String { get }
}

// OpenAI implementation
class OpenAIService: AIServiceProtocol {
    private let apiKey: String
    private let model: String = "gpt-4o-mini"

    func summarize(
        title: String,
        content: String,
        url: String
    ) async throws -> String {
        // OpenAI API implementation
    }

    var isAvailable: Bool {
        !apiKey.isEmpty
    }

    var providerName: String { "OpenAI" }
}

// Future: Claude implementation
class ClaudeService: AIServiceProtocol {
    // Anthropic API implementation
}

// Future: Apple Intelligence implementation
@available(iOS 18.0, *)
class AppleIntelligenceService: AIServiceProtocol {
    // Foundation Models integration
}

// Service factory
class AIServiceFactory {
    static func createService(
        type: AIServiceType,
        configuration: AIConfiguration
    ) -> AIServiceProtocol {
        switch type {
        case .openAI:
            return OpenAIService(apiKey: configuration.apiKey)
        case .claude:
            return ClaudeService(apiKey: configuration.apiKey)
        case .appleIntelligence:
            if #available(iOS 18.0, *) {
                return AppleIntelligenceService()
            } else {
                fatalError("Apple Intelligence requires iOS 18+")
            }
        }
    }
}
```

### 6.4 iOS-Specific Implementations

**Storage:**
* **SwiftData** (iOS 17+) or **CoreData** for database (replaces Room)
* **Keychain** for API key storage (replaces EncryptedSharedPreferences)
* **UserDefaults** for settings (replaces SharedPreferences)
* **FileManager** for EPUB storage (use Documents directory)

**Background Work:**
* **BackgroundTasks framework** (replaces WorkManager)
* `BGProcessingTask` for digest generation
* Schedule with `BGTaskScheduler`
* Constraints: network required, charging preferred

**HTML Parsing:**
* **SwiftSoup** (port of Jsoup) for HTML parsing
* Research Swift alternatives to Readability4J (or port the algorithm)
* Consider **Readability.swift** or custom implementation

**RSS Parsing:**
* **FeedKit** or **SwiftRSS** for RSS/Atom parsing

**EPUB Generation:**
* Research Swift EPUB libraries (limited options)
* Consider **ZIPFoundation** + manual EPUB structure
* Port essential epublib functionality if needed

**Networking:**
* **URLSession** with async/await (replaces OkHttp + Retrofit)
* Configure 60-second timeouts
* Use **Codable** for JSON parsing

### 6.5 UI Considerations

**SwiftUI vs Jetpack Compose:**
* Similar declarative paradigms
* Use `@StateObject` and `@Published` (replaces StateFlow)
* Navigation: NavigationStack (iOS 16+) or NavigationView
* Dialogs: `.sheet()` and `.alert()` modifiers

**E-Ink Optimization:**
* High contrast color scheme (black/white)
* Disable animations: `.animation(.none)`
* Simple transitions
* Large, readable fonts (SF Pro Text or system serif)

### 6.6 Platform Feature Parity Checklist

- [ ] Feed management (add/edit/delete)
- [ ] Per-feed processing mode selection
- [ ] Per-feed max articles limit
- [ ] Smart content analysis and fetching
- [ ] FIDELITY mode (full article extraction)
- [ ] BRIEFING mode (AI summarization with protocol-based provider)
- [ ] OpenAI integration
- [ ] Encrypted API key storage (Keychain)
- [ ] Markdown to HTML conversion
- [ ] EPUB generation with styling
- [ ] Background digest generation (BGProcessingTask)
- [ ] User-configurable schedule time
- [ ] Manual "Run Now" trigger
- [ ] Digest history with retention policy (30 max)
- [ ] View EPUBs in external reader (share sheet)
- [ ] Delete digests with confirmation
- [ ] Minimum word count filter
- [ ] Incremental vs full fetch support
- [ ] Parallel feed fetching
- [ ] Error handling and fallbacks
- [ ] Statistics tracking (briefing/fidelity counts)

### 6.7 Future Enhancements (iOS-Specific)

* **Widgets:** Today View or Lock Screen widget for digest status
* **Shortcuts:** Siri Shortcuts for manual digest trigger
* **Apple Intelligence:** On-device summarization (iOS 18+)
* **iCloud Sync:** Feed configuration sync across devices
* **Share Extension:** Add articles directly from Safari
* **Focus Modes:** Integration with Focus mode for scheduling
* **Handoff:** Continue reading across devices