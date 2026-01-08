# Software Development Specification: Epilogue

**Version:** 1.0 (MVP)
**Project Name:** Epilogue
**Target Platform:** Android 13+ (Optimized for E-ink / Onyx Boox Palma 2)
**Language:** Kotlin
**Architecture:** MVVM with Clean Architecture principles

---

## 1. Product Overview

**Epilogue** is an Android application that serves as a personal "closing ceremony" for the information diet. It aggregates content from RSS feeds, blogs, and social media bridges, filters it through a user-defined processing engine (AI summary or Direct Compilation), and compiles it into a clean, distraction-free EPUB file on a daily schedule.

**Core Value:** Automates the creation of a personalized "daily newspaper" for offline reading, specifically tailored to the constraints and strengths of e-ink devices.

---

## 2. Functional Requirements

### 2.1 Content Aggregation (Input)

* **RSS/Atom Support:** The app must accept standard RSS and Atom feed URLs.
* **Feed Management:** Users can Add, Edit, and Delete feeds.
* **Feed Metadata:** Each feed object must contain:
* `URL`: The source address.
* `Nickname`: User-defined label (e.g., "Hacker News").
* `Processing Mode`: Enum (`FIDELITY` or `BRIEFING`).



### 2.2 Content Processing (The Pipeline)

The app must support two distinct processing modes per feed:

* **Mode A: Fidelity (Direct Compilation)**
* **Goal:** Deep reading of long-form content.
* **Logic:** Fetch URL  Extract Full Content (using `Readability4J`)  Sanitize HTML.
* **Output:** Full article text with original structure (headers, bolding) preserved. Sidebar/Ads removed.
* **Filtering:** Option to skip articles < 300 words (configurable globally).


* **Mode B: Briefing (AI Summarization)**
* **Goal:** Rapid catch-up on high-volume news.
* **Logic:** Fetch URL  Extract Text  Send to LLM API  Receive Markdown Summary.
* **LLM Integration:**
* User must supply their own API Key (initially supporting OpenAI).
* System Prompt must enforce a "neutral editor" tone suitable for bedtime reading.


* **Output:** A structured summary (Hook, Key Details, Significance).



### 2.3 EPUB Generation (Output)

* **File Format:** Standard `.epub` file.
* **Naming Convention:** `Epilogue_YYYY-MM-DD.epub`
* **Structure:**
* **Cover Page:** Title ("Epilogue") + Date.
* **Table of Contents (TOC):** Navigable links to all articles.
* **Section 1: The Briefing:** All AI summaries compiled into one continuous chapter.
* **Section 2: Deep Dives:** Full-text articles, each as a separate chapter.


* **Storage:** Save files to `/Documents/Epilogue/` (public directory).

### 2.4 Automation & System Integration

* **Scheduling:** User-defined execution time (e.g., 10:00 PM).
* **Background Execution:** Must run reliably via `WorkManager` (PeriodicWorkRequest) even if the app is closed.
* **Media Scan:** Must trigger `MediaScannerConnection` immediately after saving. This is critical for the file to appear in the Boox Library widget without a device reboot.

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

### 3.3 UI/UX Constraints (E-Ink Optimization)

* **Theme:** High Contrast Mode. Pure Black (#000000) text on Pure White (#FFFFFF) background.
* **Motion:** `windowAnimationScale` set to 0 locally or animations globally disabled in Compose.
* **Typography:** Use a high-legibility serif font (e.g., Merriweather) for preview screens.

### 3.4 Data Models

**Entity: Feed**

```kotlin
@Entity(tableName = "feeds")
data class Feed(
    @PrimaryKey val url: String,
    val name: String,
    val mode: ProcessingMode, // Enum: FIDELITY, BRIEFING
    val lastFetched: Long = 0L
)

```

**Entity: ProcessedArticle (Transient)**

```kotlin
data class ProcessedArticle(
    val title: String,
    val author: String,
    val content: String, // HTML or Markdown
    val originalUrl: String,
    val isSummary: Boolean
)

```

---

## 4. Implementation Plan

### **Phase 1: Skeleton & Feed Management**

**Goal:** A working app that can save RSS URLs to a database and display them in a list.

* **1.1 Setup:** Initialize Android project (Compose, Hilt, Room). Add `INTERNET` and `READ/WRITE_EXTERNAL_STORAGE` (if needed for older SDKs) permissions.
* **1.2 DB:** Implement `Feed` Room Entity and DAO.
* **1.3 UI:** Create "Feed Manager" screen.
* Input: URL + Nickname + Mode Toggle.
* Validation: Use `RSS-Parser` to verify URL is valid before saving.



### **Phase 2: The Fetch & Clean Pipeline**

**Goal:** Manually trigger a fetch that downloads article text (no EPUB yet).

* **2.1 Repository:** Implement `ArticleRepository`. Function `fetchArticles(feedUrl)` returns list of raw items.
* **2.2 Processing Service:** Create `ContentProcessor` class.
* Integrate `Readability4J`.
* Logic: Input URL  Jsoup Fetch  Readability Parse  Output Clean HTML string.


* **2.3 Logic:** Add "New Content Only" filter (compare article date vs. `lastFetched`).

### **Phase 3: The EPUB Generator & AI**

**Goal:** Generate a physical file and add AI intelligence.

* **3.1 Generator:** Implement `EpubGenerator` wrapper around `epublib`.
* Input: List of `ProcessedArticle`.
* Output: File written to `/Documents/Epilogue/`.


* **3.2 AI Integration:** Create `OpenAIService`.
* Securely handle API Key input (store in `EncryptedSharedPreferences`).
* Implement "Briefing" logic: if Feed Mode == BRIEFING, swap full text for API response.


* **3.3 Link:** Connect `ContentProcessor` output to `EpubGenerator` input.

### **Phase 4: Automation & E-ink Polish**

**Goal:** "Set and Forget."

* **4.1 Worker:** Implement `DailyDigestWorker` using `WorkManager`.
* Constraints: `NetworkType.CONNECTED`, `BatteryNotLow`.


* **4.2 Media Scanner:** Add the `MediaScannerConnection` utility to auto-refresh the Boox Library.
* **4.3 Polish:** Ensure UI is strictly B&W. Add "Run Now" button for testing.

---

## 5. Agent Instructions (Prompt Templates)

*Use these prompts when asking an AI to code specific sections.*

**Prompt for Phase 2 (The Scraper):**

> "I need to implement the Content Processing pipeline for the app 'Epilogue'. Reference section 2.2 of the spec.
> Please create a `ContentProcessor` class in Kotlin.
> 1. It must take a URL string as input.
> 2. Use `Jsoup` to fetch the raw HTML.
> 3. Use `Readability4J` to extract the main article content (title + body).
> 4. Handle exceptions gracefully (return null if the page fails to parse).
> 5. Create a simple Unit Test using a sample URL (e.g., a blog post) to verify it strips the sidebar."
> 
> 

**Prompt for Phase 3 (The Generator):**

> "We are building the Output engine for 'Epilogue'. Implement the `EpubGenerator` class using the `epublib` library.
> It needs a function `generate(articles: List<ProcessedArticle>, outputDir: File): File`.
> Requirements:
> 1. Create a Table of Contents.
> 2. Separate 'Summaries' (Section 1) from 'Full Articles' (Section 2).
> 3. Save the file as `Epilogue_{Date}.epub`.
> 4. Crucial: Include a helper function `scanFile(context, file)` that triggers the Android MediaScanner so the file is visible to other apps immediately."
> 
>