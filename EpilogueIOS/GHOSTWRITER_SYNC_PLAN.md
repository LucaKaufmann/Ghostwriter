# Ghostwriter Sync Implementation Plan - iOS

## Overview

Port the Ghostwriter server sync functionality from the Android app to iOS. This enables bi-directional sync of feeds, digests, and configuration between the iOS app and a self-hosted Ghostwriter server.

---

## Ghostwriter API Summary

### Base URL
Configured by user (e.g., `https://ghostwriter.example.com`)

### Authentication
- `Authorization: Bearer <API_KEY>` header on all authenticated endpoints

### Key Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check (no auth) |
| `/feeds` | GET | List all feeds |
| `/feeds/sync` | POST | Bulk sync feeds (additive merge) |
| `/feeds/changes` | GET | Incremental feed sync with tombstones |
| `/feeds/by-url/{url}` | DELETE | Soft-delete feed by URL |
| `/digests` | GET | List digests |
| `/digests/trigger` | POST | Trigger manual digest generation |
| `/digests/{id}/status` | GET | Poll digest job progress |
| `/digests/{id}/articles` | GET | Get articles with content |
| `/digests/{filename}` | GET | Download EPUB file |
| `/config` | GET/PUT | Shared client configuration |
| `/client/heartbeat` | POST | Send activity heartbeat |
| `/client/status` | GET | Get activity tracking info |

---

## Implementation Phases

### Phase 1: Networking Layer (New Module)

Create a new `GhostwriterClient` module.

**Files to create:**

```
Modules/GhostwriterClient/
├── Project.swift
├── Sources/
│   ├── GhostwriterClient.swift      # Main client class
│   ├── GhostwriterAPI.swift         # Endpoint definitions
│   ├── Models/
│   │   ├── FeedModels.swift         # FeedSyncRequest, FeedResponse, FeedChangesResponse
│   │   ├── DigestModels.swift       # DigestResponse, DigestStatusResponse, DigestArticlesResponse
│   │   ├── ConfigModels.swift       # ClientConfigResponse, ClientConfigUpdateRequest
│   │   ├── ClientModels.swift       # HeartbeatResponse, ClientStatusResponse
│   │   └── HealthModels.swift       # HealthResponse
│   └── GhostwriterError.swift       # Custom error types
└── Tests/
    └── GhostwriterClientTests.swift
```

**Key Models (Swift):**

```swift
// FeedModels.swift
struct FeedSyncRequest: Codable {
    let url: String
    let title: String
    let isActive: Bool
    let mode: String  // "raw" or "summarize"
    let maxArticles: Int
    
    enum CodingKeys: String, CodingKey {
        case url, title, mode
        case isActive = "is_active"
        case maxArticles = "max_articles"
    }
}

struct FeedResponse: Codable {
    let id: String
    let url: String
    let title: String
    let isActive: Bool
    let mode: String
    let maxArticles: Int
    let createdAt: String
    let updatedAt: String
    
    enum CodingKeys: String, CodingKey {
        case id, url, title, mode
        case isActive = "is_active"
        case maxArticles = "max_articles"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }
}

struct FeedTombstone: Codable {
    let url: String
    let deletedAt: String
    
    enum CodingKeys: String, CodingKey {
        case url
        case deletedAt = "deleted_at"
    }
}

struct FeedChangesResponse: Codable {
    let feeds: [FeedResponse]
    let tombstones: [FeedTombstone]
    let serverTimestamp: String
    
    enum CodingKeys: String, CodingKey {
        case feeds, tombstones
        case serverTimestamp = "server_timestamp"
    }
}

// DigestModels.swift
struct DigestResponse: Codable {
    let id: String
    let filename: String
    let period: String
    let status: String
    let stage: String?
    let articleCount: Int
    let errorMessage: String?
    let createdAt: String
    let completedAt: String?
    let downloadedAt: String?
    
    enum CodingKeys: String, CodingKey {
        case id, filename, period, status, stage
        case articleCount = "article_count"
        case errorMessage = "error_message"
        case createdAt = "created_at"
        case completedAt = "completed_at"
        case downloadedAt = "downloaded_at"
    }
}

struct DigestProgress: Codable {
    let totalFeeds: Int
    let feedsFetched: Int
    let totalArticles: Int
    let articlesEnriched: Int
    
    enum CodingKeys: String, CodingKey {
        case totalFeeds = "total_feeds"
        case feedsFetched = "feeds_fetched"
        case totalArticles = "total_articles"
        case articlesEnriched = "articles_enriched"
    }
}

struct DigestStatusResponse: Codable {
    let id: String
    let status: String
    let stage: String?
    let progress: DigestProgress
    let startedAt: String
    let etaSeconds: Int?
    
    enum CodingKeys: String, CodingKey {
        case id, status, stage, progress
        case startedAt = "started_at"
        case etaSeconds = "eta_seconds"
    }
}

struct DigestArticleResponse: Codable {
    let id: String
    let title: String
    let url: String
    let mode: String
    let wordCount: Int
    let content: String
    let author: String?
    let feedTitle: String
    let sortOrder: Int
    let aiFailed: Bool
    
    enum CodingKeys: String, CodingKey {
        case id, title, url, mode, content, author
        case wordCount = "word_count"
        case feedTitle = "feed_title"
        case sortOrder = "sort_order"
        case aiFailed = "ai_failed"
    }
}

struct DigestArticlesResponse: Codable {
    let digestId: String
    let articleCount: Int
    let articles: [DigestArticleResponse]
    
    enum CodingKeys: String, CodingKey {
        case digestId = "digest_id"
        case articleCount = "article_count"
        case articles
    }
}
```

**GhostwriterClient.swift:**

```swift
import Foundation

actor GhostwriterClient {
    private let baseURL: URL
    private let apiKey: String?
    private let session: URLSession
    
    enum GhostwriterError: Error {
        case notConfigured
        case invalidURL
        case networkError(Error)
        case httpError(statusCode: Int, message: String)
        case decodingError(Error)
        case conflict(message: String)
    }
    
    init(baseURL: URL, apiKey: String? = nil) {
        self.baseURL = baseURL
        self.apiKey = apiKey
        self.session = URLSession.shared
    }
    
    // MARK: - Feeds
    
    func syncFeeds(_ feeds: [FeedSyncRequest]) async throws -> FeedSyncResponse
    func getFeedChanges(since: Date?) async throws -> FeedChangesResponse
    func deleteFeed(byURL url: String) async throws
    
    // MARK: - Digests
    
    func listDigests() async throws -> [DigestResponse]
    func triggerDigest(period: String = "manual") async throws -> DigestTriggerResponse
    func getDigestStatus(id: String) async throws -> DigestStatusResponse
    func getDigestArticles(id: String) async throws -> DigestArticlesResponse
    func downloadDigest(filename: String) async throws -> Data
    
    // MARK: - Config
    
    func getConfig() async throws -> ClientConfigResponse
    func updateConfig(_ request: ClientConfigUpdateRequest) async throws -> ClientConfigResponse
    
    // MARK: - Client Activity
    
    func sendHeartbeat() async throws -> HeartbeatResponse
    func getClientStatus() async throws -> ClientStatusResponse
    
    // MARK: - Health
    
    func checkHealth() async throws -> HealthResponse
}
```

---

### Phase 2: Settings & Keychain Storage

**Updates to Data module:**

Add Ghostwriter settings to `SettingsRepository`:

```swift
// Add to existing SettingsRepository or create GhostwriterSettings
struct GhostwriterSettings: Codable {
    var isEnabled: Bool = false
    var serverURL: String?
    var lastFeedSyncTime: Date?
    var lastDigestSyncTime: Date?
    var configUpdatedAt: String?
}

// Store API key in Keychain (not UserDefaults!)
class GhostwriterKeychain {
    static func saveAPIKey(_ key: String) throws
    static func getAPIKey() -> String?
    static func deleteAPIKey() throws
}
```

---

### Phase 3: Data Layer Updates

**Updates to Domain module:**

Add fields to `Feed` model:
```swift
struct Feed {
    // ... existing fields ...
    var serverUpdatedAt: Date?
    var locallyModified: Bool = false
}
```

**Updates to Data module:**

Add `remoteId` to `Digest` entity for tracking server-synced digests.

Add repository methods:
```swift
// FeedRepository additions
func upsertAll(_ feeds: [Feed]) async throws
func deleteByURLs(_ urls: [String]) async throws
func clearAllLocallyModified() async throws
func getLocallyModifiedFeeds() async -> [Feed]

// DigestRepository additions  
func saveRemoteDigest(remoteId: String, ..., articles: [DigestArticleResponse]?) async throws
func getAllRemoteIds() async -> [String]
```

---

### Phase 4: Sync Services

Create sync service classes in the App target:

**FeedSyncService.swift:**
```swift
class FeedSyncService {
    private let client: GhostwriterClient
    private let feedRepository: FeedRepository
    private let settings: GhostwriterSettings
    
    /// Bi-directional feed sync
    /// 1. PUSH: Local feeds → Server
    /// 2. PULL: Server changes → Local (with tombstones)
    func sync() async throws {
        guard settings.isEnabled else { return }
        
        // Push local feeds
        let localFeeds = await feedRepository.getAllFeeds()
        let syncRequests = localFeeds.map { $0.toSyncRequest() }
        _ = try await client.syncFeeds(syncRequests)
        
        // Pull changes from server
        let changes = try await client.getFeedChanges(since: settings.lastFeedSyncTime)
        
        // Apply server feeds
        let serverFeeds = changes.feeds.map { Feed(from: $0) }
        try await feedRepository.upsertAll(serverFeeds)
        
        // Apply tombstones (delete locally)
        let tombstoneURLs = changes.tombstones.map { $0.url }
        try await feedRepository.deleteByURLs(tombstoneURLs)
        
        // Clear local modification flags
        try await feedRepository.clearAllLocallyModified()
        
        // Update sync timestamp
        settings.lastFeedSyncTime = changes.serverTimestamp.toDate()
    }
}
```

**DigestSyncService.swift:**
```swift
class DigestSyncService {
    private let client: GhostwriterClient
    private let digestRepository: DigestRepository
    private let settings: GhostwriterSettings
    
    /// Check for new digests and download them
    func sync() async throws {
        guard settings.isEnabled else { return }
        
        let remoteDigests = try await client.listDigests()
        let existingIds = Set(await digestRepository.getAllRemoteIds())
        
        // Filter to new completed digests
        let newDigests = remoteDigests.filter { 
            $0.status == "completed" && !existingIds.contains($0.id)
        }
        
        for digest in newDigests {
            // Download EPUB
            let epubData = try await client.downloadDigest(filename: digest.filename)
            let localURL = try saveEPUB(data: epubData, filename: digest.filename)
            
            // Fetch articles for in-app display
            let articles = try? await client.getDigestArticles(id: digest.id)
            
            // Save to local database
            try await digestRepository.saveRemoteDigest(
                remoteId: digest.id,
                epubFilePath: localURL.path,
                articleCount: digest.articleCount,
                generatedAt: digest.completedAt?.toDate() ?? Date(),
                period: digest.period,
                articles: articles?.articles
            )
        }
        
        settings.lastDigestSyncTime = Date()
    }
}
```

**ConfigSyncManager.swift:**
```swift
class ConfigSyncManager {
    private let client: GhostwriterClient
    private let settings: SettingsRepository
    
    /// Sync config on app launch (last-write-wins)
    func sync() async throws {
        guard settings.isGhostwriterEnabled else { return }
        
        let serverConfig = try await client.getConfig()
        let localUpdatedAt = settings.configUpdatedAt
        
        if localUpdatedAt == nil {
            // First sync - apply server config
            applyServerConfig(serverConfig)
        } else {
            let serverTime = serverConfig.updatedAt.toDate()
            let localTime = localUpdatedAt!.toDate()
            
            if serverTime > localTime {
                applyServerConfig(serverConfig)
            } else if localTime > serverTime {
                try await pushLocalConfig()
            }
        }
    }
}
```

---

### Phase 5: Background Tasks

Use `BGAppRefreshTask` for periodic sync:

```swift
// In AppDelegate or App struct
func registerBackgroundTasks() {
    BGTaskScheduler.shared.register(
        forTaskWithIdentifier: "com.epilogue.feedSync",
        using: nil
    ) { task in
        self.handleFeedSync(task: task as! BGAppRefreshTask)
    }
    
    BGTaskScheduler.shared.register(
        forTaskWithIdentifier: "com.epilogue.digestSync", 
        using: nil
    ) { task in
        self.handleDigestSync(task: task as! BGAppRefreshTask)
    }
}

func scheduleBackgroundSync() {
    let feedRequest = BGAppRefreshTaskRequest(identifier: "com.epilogue.feedSync")
    feedRequest.earliestBeginDate = Date(timeIntervalSinceNow: 15 * 60) // 15 min
    try? BGTaskScheduler.shared.submit(feedRequest)
    
    let digestRequest = BGAppRefreshTaskRequest(identifier: "com.epilogue.digestSync")
    digestRequest.earliestBeginDate = Date(timeIntervalSinceNow: 30 * 60) // 30 min
    try? BGTaskScheduler.shared.submit(digestRequest)
}
```

---

### Phase 6: Settings UI

Add Ghostwriter configuration screen:

```swift
struct GhostwriterSettingsView: View {
    @State private var isEnabled = false
    @State private var serverURL = ""
    @State private var apiKey = ""
    @State private var connectionStatus: ConnectionStatus = .unknown
    
    var body: some View {
        Form {
            Section("Server") {
                Toggle("Enable Ghostwriter Sync", isOn: $isEnabled)
                
                TextField("Server URL", text: $serverURL)
                    .keyboardType(.URL)
                    .autocapitalization(.none)
                
                SecureField("API Key", text: $apiKey)
            }
            
            Section {
                Button("Test Connection") {
                    Task { await testConnection() }
                }
                
                if case .connected(let health) = connectionStatus {
                    Text("Connected to \(health.version)")
                        .foregroundColor(.green)
                }
            }
            
            Section("Sync") {
                Button("Sync Feeds Now") { ... }
                Button("Sync Digests Now") { ... }
                
                if let lastSync = settings.lastFeedSyncTime {
                    Text("Last feed sync: \(lastSync.formatted())")
                }
            }
        }
        .navigationTitle("Ghostwriter")
    }
}
```

---

## File Checklist

### New Module: GhostwriterClient
- [ ] `Modules/GhostwriterClient/Project.swift`
- [ ] `Sources/GhostwriterClient.swift`
- [ ] `Sources/GhostwriterAPI.swift`
- [ ] `Sources/GhostwriterError.swift`
- [ ] `Sources/Models/FeedModels.swift`
- [ ] `Sources/Models/DigestModels.swift`
- [ ] `Sources/Models/ConfigModels.swift`
- [ ] `Sources/Models/ClientModels.swift`
- [ ] `Sources/Models/HealthModels.swift`
- [ ] `Tests/GhostwriterClientTests.swift`

### Updates to Data Module
- [ ] `GhostwriterSettings.swift`
- [ ] `GhostwriterKeychain.swift`
- [ ] Update `FeedEntity` (add `serverUpdatedAt`, `locallyModified`)
- [ ] Update `DigestEntity` (add `remoteId`)
- [ ] Update `FeedRepository` (upsert, delete by URLs, etc.)
- [ ] Update `DigestRepository` (save remote digest)

### Updates to Domain Module
- [ ] Update `Feed` model
- [ ] Update `Digest` model

### App Target
- [ ] `Services/FeedSyncService.swift`
- [ ] `Services/DigestSyncService.swift`
- [ ] `Services/ConfigSyncManager.swift`
- [ ] `Services/HeartbeatService.swift`
- [ ] `Views/Settings/GhostwriterSettingsView.swift`
- [ ] Update `Info.plist` (background task identifiers)
- [ ] Register background tasks in app lifecycle

---

## Sync Behavior Summary

| Sync Type | Trigger | Direction | Conflict Resolution |
|-----------|---------|-----------|---------------------|
| Feed Sync | App launch, background, manual | Bi-directional | Server wins (tombstones respected) |
| Digest Sync | App launch, background, manual | Pull only | N/A (server is source of truth) |
| Config Sync | App launch, settings change | Bi-directional | Last-write-wins by timestamp |
| Heartbeat | App launch, background | Push only | N/A |

---

## Testing Plan

1. **Unit Tests**
   - GhostwriterClient request/response encoding
   - Sync service logic (mock client)
   - Conflict resolution

2. **Integration Tests**
   - Full sync flow with local Ghostwriter server
   - Background task execution

3. **Manual Testing**
   - Add feed on iOS → appears on Android/web
   - Delete feed on server → removed from iOS
   - Generate digest on server → downloaded to iOS
   - Config change on iOS → synced to server

---

## Estimated Effort

| Phase | Effort |
|-------|--------|
| Phase 1: Networking | 3-4 hours |
| Phase 2: Settings/Keychain | 1-2 hours |
| Phase 3: Data Layer | 2-3 hours |
| Phase 4: Sync Services | 3-4 hours |
| Phase 5: Background Tasks | 2-3 hours |
| Phase 6: Settings UI | 2-3 hours |
| **Total** | **13-19 hours** |
