//
//  GhostwriterClient.swift
//  Epilogue
//
//  Created on 2026-01-26.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import Foundation
import OSLog
#if canImport(EpilogueShared)
import EpilogueShared
#endif

// MARK: - URLSession Metrics Delegate

/// Helper class to capture URLSession task metrics (used opt-in).
/// Not an actor so it can serve as a delegate.
public final class GhostwriterMetricsDelegate: NSObject, URLSessionTaskDelegate, @unchecked Sendable {
    private let logger = Logger(subsystem: "com.epilogue", category: "NetworkMetrics")
    private let lock = NSLock()
    private var _lastMetricsSummary: RequestMetricsSummary?

    /// Summary of the last completed request's network metrics
    public struct RequestMetricsSummary: Sendable {
        public let dnsLookupMs: Double?
        public let tlsHandshakeMs: Double?
        public let ttfbMs: Double?
        public let totalTransferMs: Double?
        public let responseBytes: Int64?
    }

    public var lastMetricsSummary: RequestMetricsSummary? {
        lock.withLock { _lastMetricsSummary }
    }

    public func urlSession(_ session: URLSession, task: URLSessionTask, didFinishCollecting metrics: URLSessionTaskMetrics) {
        guard let tx = metrics.transactionMetrics.last else { return }

        let dns: Double? = {
            guard let start = tx.domainLookupStartDate, let end = tx.domainLookupEndDate else { return nil }
            return end.timeIntervalSince(start) * 1000
        }()

        let tls: Double? = {
            guard let start = tx.secureConnectionStartDate, let end = tx.secureConnectionEndDate else { return nil }
            return end.timeIntervalSince(start) * 1000
        }()

        let ttfb: Double? = {
            guard let reqEnd = tx.requestEndDate, let respStart = tx.responseStartDate else { return nil }
            return respStart.timeIntervalSince(reqEnd) * 1000
        }()

        let total: Double? = {
            guard let start = tx.fetchStartDate, let end = tx.responseEndDate else { return nil }
            return end.timeIntervalSince(start) * 1000
        }()

        let bytes = tx.countOfResponseBodyBytesReceived

        let summary = RequestMetricsSummary(
            dnsLookupMs: dns,
            tlsHandshakeMs: tls,
            ttfbMs: ttfb,
            totalTransferMs: total,
            responseBytes: bytes
        )

        lock.withLock { _lastMetricsSummary = summary }

        logger.debug("Network metrics — DNS: \(dns.map { String(format: "%.1f", $0) } ?? "-")ms, TLS: \(tls.map { String(format: "%.1f", $0) } ?? "-")ms, TTFB: \(ttfb.map { String(format: "%.1f", $0) } ?? "-")ms, transfer: \(total.map { String(format: "%.1f", $0) } ?? "-")ms, bytes: \(bytes)")
    }
}

/// Client for interacting with the Ghostwriter backend API
public actor GhostwriterClient {
    
    // MARK: - Properties
    
    private let baseURL: URL
    private let apiKey: String?
    private let session: URLSession
    private let decoder: JSONDecoder
    private let encoder: JSONEncoder
    private let perfLogger = Logger(subsystem: "com.epilogue", category: "GhostwriterRequests")
    private let metricsDelegate: GhostwriterMetricsDelegate?
#if canImport(EpilogueShared)
    private let sharedHandle: GhostwriterClientHandle?
#endif
    
    // MARK: - Initialization
    
    /// Create a new Ghostwriter client
    /// - Parameters:
    ///   - baseURL: The base URL of the Ghostwriter server
    ///   - apiKey: Optional API key for authentication
    ///   - session: URLSession to use for requests (defaults to shared)
    ///   - enableMetrics: Whether to capture URLSession task metrics (creates a custom session)
    public init(baseURL: URL, apiKey: String? = nil, session: URLSession = .shared, enableMetrics: Bool = {
        #if DEBUG
        return true
        #else
        return false
        #endif
    }(), useSharedClient: Bool = false) {
        // Ensure base URL includes /api/ path
        if baseURL.pathComponents.contains("api") {
            self.baseURL = baseURL
        } else {
            self.baseURL = baseURL.appendingPathComponent("api")
        }
        self.apiKey = apiKey
        
        if enableMetrics {
            let delegate = GhostwriterMetricsDelegate()
            self.metricsDelegate = delegate
            self.session = URLSession(configuration: session.configuration, delegate: delegate, delegateQueue: nil)
        } else {
            self.metricsDelegate = nil
            self.session = session
        }
        
        self.decoder = JSONDecoder()
        self.encoder = JSONEncoder()

#if canImport(EpilogueShared)
        if useSharedClient {
            self.sharedHandle = GhostwriterClientHandle.companion.create(
                baseUrl: self.baseURL.absoluteString,
                apiKey: apiKey
            )
        } else {
            self.sharedHandle = nil
        }
#endif
    }
    
    /// Convenience initializer from URL string
    public init(baseURLString: String, apiKey: String? = nil, enableMetrics: Bool = {
        #if DEBUG
        return true
        #else
        return false
        #endif
    }(), useSharedClient: Bool = false) throws {
        guard let url = URL(string: baseURLString) else {
            throw GhostwriterError.invalidURL(baseURLString)
        }
        self.init(baseURL: url, apiKey: apiKey, enableMetrics: enableMetrics, useSharedClient: useSharedClient)
    }
    
    /// Get the last request's network metrics summary (only available when enableMetrics is true)
    public func getLastMetricsSummary() -> GhostwriterMetricsDelegate.RequestMetricsSummary? {
        metricsDelegate?.lastMetricsSummary
    }
    
    // MARK: - Combined Sync
    
    /// Perform a combined sync that returns config, feeds, digests, and schedules in one call.
    /// - Parameters:
    ///   - feedSince: Optional date for incremental feed sync
    ///   - knownDigestIds: List of digest IDs the client already has (excluded from response)
    /// - Returns: Combined sync response
    public func performSync(feedSince: Date? = nil, knownDigestIds: [String] = []) async throws -> SyncResponse {
#if canImport(EpilogueShared)
        if let sharedHandle {
            let formatter = ISO8601DateFormatter()
            formatter.formatOptions = [.withInternetDateTime]
            let feedSinceString = feedSince.map { formatter.string(from: $0) }
            let digestIds = knownDigestIds.isEmpty ? nil : knownDigestIds.joined(separator: ",")
            let sharedResponse = try await sharedHandle.client.performSync(
                feedSince: feedSinceString,
                digestIds: digestIds
            )

            let config = ClientConfigResponse(
                minWordCount: sharedResponse.config.minWordCount.map { Int(truncating: $0) },
                morningHour: sharedResponse.config.morningHour.map { Int(truncating: $0) },
                morningMinute: sharedResponse.config.morningMinute.map { Int(truncating: $0) },
                noonHour: sharedResponse.config.noonHour.map { Int(truncating: $0) },
                noonMinute: sharedResponse.config.noonMinute.map { Int(truncating: $0) },
                eveningHour: sharedResponse.config.eveningHour.map { Int(truncating: $0) },
                eveningMinute: sharedResponse.config.eveningMinute.map { Int(truncating: $0) },
                timezone: sharedResponse.config.timezone,
                aiProvider: nil,
                aiModel: nil,
                scheduleMorning: sharedResponse.config.scheduleMorning,
                scheduleNoon: sharedResponse.config.scheduleNoon,
                scheduleEvening: sharedResponse.config.scheduleEvening,
                whisperProvider: sharedResponse.config.whisperProvider,
                whisperModel: sharedResponse.config.whisperModel,
                whisperTimeoutMinutes: sharedResponse.config.whisperTimeoutMinutes.map { Int(truncating: $0) },
                mediaProcessingIntervalHours: sharedResponse.config.mediaProcessingIntervalHours.map { Int(truncating: $0) },
                includePodcastsInDigest: sharedResponse.config.includePodcastsInDigest?.boolValue,
                includeYoutubeInDigest: sharedResponse.config.includeYoutubeInDigest?.boolValue,
                coverEnabled: sharedResponse.config.coverEnabled?.boolValue,
                coverProvider: sharedResponse.config.coverProvider,
                coverQuality: sharedResponse.config.coverQuality,
                coverPrompt: sharedResponse.config.coverPrompt,
                coverOverlayEnabled: sharedResponse.config.coverOverlayEnabled?.boolValue,
                coverOpenAIAPIKey: sharedResponse.config.coverOpenAiApiKey,
                coverGeminiAPIKey: sharedResponse.config.coverGeminiApiKey,
                updatedAt: sharedResponse.config.updatedAt,
                wallabag: sharedResponse.config.wallabag.map { IntegrationStatus(enabled: $0.enabled, label: $0.label) },
                newsletters: sharedResponse.config.newsletters.map { IntegrationStatus(enabled: $0.enabled, label: $0.label) }
            )

            let feeds = FeedChangesResponse(
                feeds: sharedResponse.feeds.feeds.map { feed in
                    FeedResponse(
                        id: feed.id,
                        url: feed.url,
                        title: feed.title,
                        isActive: feed.isActive,
                        mode: feed.mode,
                        maxArticles: Int(feed.maxArticles),
                        createdAt: feed.createdAt,
                        updatedAt: feed.updatedAt,
                        deletedAt: feed.deletedAt
                    )
                },
                tombstones: sharedResponse.feeds.tombstones.map { tombstone in
                    FeedTombstone(
                        url: tombstone.url,
                        deletedAt: tombstone.deletedAt
                    )
                },
                serverTimestamp: sharedResponse.feeds.serverTimestamp
            )

            let digests = SyncDigestsSection(
                newDigests: sharedResponse.digests.newDigests.map { digest in
                    SyncDigest(
                        id: digest.id,
                        filename: digest.filename,
                        period: digest.period,
                        status: digest.status,
                        stage: digest.stage,
                        articleCount: Int(digest.articleCount),
                        errorMessage: digest.errorMessage,
                        createdAt: digest.createdAt,
                        completedAt: digest.completedAt,
                        articles: digest.articles.map { article in
                            DigestArticleResponse(
                                id: article.id,
                                title: article.title,
                                url: article.url,
                                mode: article.mode,
                                wordCount: Int(article.wordCount),
                                content: article.content,
                                author: article.author,
                                feedTitle: article.feedTitle,
                                sortOrder: Int(article.sortOrder),
                                aiFailed: article.aiFailed
                            )
                        }
                    )
                }
            )

            let schedules = sharedResponse.schedules.map { schedule in
                ScheduleResponse(
                    id: schedule.id,
                    period: schedule.period,
                    hour: Int(schedule.hour),
                    minute: Int(schedule.minute),
                    enabled: schedule.enabled,
                    timezone: schedule.timezone,
                    nextRunAt: schedule.nextRunAt
                )
            }

            return SyncResponse(config: config, feeds: feeds, digests: digests, schedules: schedules)
        }
#endif
        var queryItems: [URLQueryItem] = []
        
        if let feedSince = feedSince {
            let formatter = ISO8601DateFormatter()
            formatter.formatOptions = [.withInternetDateTime]
            queryItems.append(URLQueryItem(name: "feed_since", value: formatter.string(from: feedSince)))
        }
        
        if !knownDigestIds.isEmpty {
            queryItems.append(URLQueryItem(name: "digest_ids", value: knownDigestIds.joined(separator: ",")))
        }
        
        return try await get(path: "/sync", queryItems: queryItems)
    }
    
    // MARK: - Health
    
    /// Check the health of the Ghostwriter server
    public func checkHealth() async throws -> HealthResponse {
#if canImport(EpilogueShared)
        if let sharedHandle {
            let sharedResponse = try await sharedHandle.client.getHealth()
            return HealthResponse(
                status: sharedResponse.status,
                version: sharedResponse.version,
                uptimeSeconds: sharedResponse.uptimeSeconds?.intValue,
                lastSuccessfulDigest: sharedResponse.lastSuccessfulDigest,
                aiProvider: sharedResponse.aiProvider,
                aiModel: sharedResponse.aiModel
            )
        }
#endif
        return try await get(path: "/health", authenticated: false)
    }
    
    // MARK: - Feeds
    
    /// List all configured feeds
    public func listFeeds() async throws -> [FeedResponse] {
#if canImport(EpilogueShared)
        if let sharedHandle {
            let sharedFeeds = try await sharedHandle.client.listFeeds()
            return sharedFeeds.map { feed in
                FeedResponse(
                    id: feed.id,
                    url: feed.url,
                    title: feed.title,
                    isActive: feed.isActive,
                    mode: feed.mode,
                    maxArticles: Int(feed.maxArticles),
                    createdAt: feed.createdAt,
                    updatedAt: feed.updatedAt,
                    deletedAt: feed.deletedAt
                )
            }
        }
#endif
        return try await get(path: "/feeds")
    }
    
    /// Sync feeds to the server (additive merge)
    /// - Parameter feeds: List of feeds to sync
    /// - Returns: Sync results showing created/updated/unchanged counts
    public func syncFeeds(_ feeds: [FeedSyncRequest]) async throws -> FeedSyncResponse {
#if canImport(EpilogueShared)
        if let sharedHandle {
            let sharedResponse = try await sharedHandle.client.syncFeeds(
                feeds: feeds.map { feed in
                    EpilogueShared.FeedSyncRequest(
                        url: feed.url,
                        title: feed.title,
                        isActive: feed.isActive,
                        mode: feed.mode,
                        maxArticles: Int32(feed.maxArticles)
                    )
                }
            )
            return FeedSyncResponse(
                synced: Int(sharedResponse.synced),
                created: Int(sharedResponse.created),
                updated: Int(sharedResponse.updated),
                unchanged: Int(sharedResponse.unchanged)
            )
        }
#endif
        return try await post(path: "/feeds/sync", body: feeds)
    }
    
    /// Get feed changes for incremental sync
    /// - Parameter since: Optional timestamp to get changes since
    /// - Returns: Feed changes including updated feeds and tombstones
    public func getFeedChanges(since: Date? = nil) async throws -> FeedChangesResponse {
#if canImport(EpilogueShared)
        if let sharedHandle {
            let formatter = ISO8601DateFormatter()
            formatter.formatOptions = [.withInternetDateTime]
            let sinceString = since.map { formatter.string(from: $0) }
            let sharedResponse = try await sharedHandle.client.getFeedChanges(since: sinceString)
            return FeedChangesResponse(
                feeds: sharedResponse.feeds.map { feed in
                    FeedResponse(
                        id: feed.id,
                        url: feed.url,
                        title: feed.title,
                        isActive: feed.isActive,
                        mode: feed.mode,
                        maxArticles: Int(feed.maxArticles),
                        createdAt: feed.createdAt,
                        updatedAt: feed.updatedAt,
                        deletedAt: feed.deletedAt
                    )
                },
                tombstones: sharedResponse.tombstones.map { tombstone in
                    FeedTombstone(
                        url: tombstone.url,
                        deletedAt: tombstone.deletedAt
                    )
                },
                serverTimestamp: sharedResponse.serverTimestamp
            )
        }
#endif
        var queryItems: [URLQueryItem] = []
        
        if let since = since {
            let formatter = ISO8601DateFormatter()
            formatter.formatOptions = [.withInternetDateTime]
            queryItems.append(URLQueryItem(name: "since", value: formatter.string(from: since)))
        }
        
        return try await get(path: "/feeds/changes", queryItems: queryItems)
    }
    
    /// Delete a feed by URL
    /// - Parameter url: The feed URL to delete
    public func deleteFeed(byURL url: String) async throws {
#if canImport(EpilogueShared)
        if let sharedHandle {
            try await sharedHandle.client.deleteFeedByUrl(feedUrl: url)
            return
        }
#endif
        guard let encodedURL = url.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) else {
            throw GhostwriterError.invalidURL(url)
        }
        
        let _: EmptyResponse = try await delete(path: "/feeds/by-url/\(encodedURL)")
    }
    
    // MARK: - Digests
    
    /// List available digests
    /// - Parameters:
    ///   - limit: Maximum number of digests to return
    ///   - offset: Offset for pagination
    ///   - status: Optional status filter
    /// - Returns: List of digests
    public func listDigests(limit: Int = 20, offset: Int = 0, status: String? = nil) async throws -> [DigestResponse] {
#if canImport(EpilogueShared)
        if let sharedHandle, limit == 20, offset == 0, status == nil {
            let digests = try await sharedHandle.client.listDigests()
            return digests.map { digest in
                DigestResponse(
                    id: digest.id,
                    filename: digest.filename,
                    period: digest.period,
                    status: digest.status,
                    stage: digest.stage,
                    articleCount: Int(digest.articleCount),
                    errorMessage: digest.errorMessage,
                    createdAt: digest.createdAt,
                    completedAt: digest.completedAt,
                    downloadedAt: nil
                )
            }
        }
#endif
        var queryItems = [
            URLQueryItem(name: "limit", value: String(limit)),
            URLQueryItem(name: "offset", value: String(offset))
        ]
        
        if let status = status {
            queryItems.append(URLQueryItem(name: "status", value: status))
        }
        
        return try await get(path: "/digests", queryItems: queryItems)
    }
    
    /// Get the most recent completed digest
    public func getLatestDigest() async throws -> DigestResponse {
#if canImport(EpilogueShared)
        if let sharedHandle {
            let digest = try await sharedHandle.client.getLatestDigest()
            return DigestResponse(
                id: digest.id,
                filename: digest.filename,
                period: digest.period,
                status: digest.status,
                stage: digest.stage,
                articleCount: Int(digest.articleCount),
                errorMessage: digest.errorMessage,
                createdAt: digest.createdAt,
                completedAt: digest.completedAt,
                downloadedAt: nil
            )
        }
#endif
        return try await get(path: "/digests/latest")
    }
    
    /// Trigger a digest generation
    /// - Parameter period: The time period ("morning", "noon", "evening", "manual")
    /// - Returns: Trigger response with digest ID
    public func triggerDigest(period: String = "manual") async throws -> DigestTriggerResponse {
#if canImport(EpilogueShared)
        if let sharedHandle {
            let sharedResponse = try await sharedHandle.client.triggerDigest(
                request: EpilogueShared.DigestTriggerRequest(period: period)
            )
            return DigestTriggerResponse(
                id: sharedResponse.id,
                status: sharedResponse.status,
                message: sharedResponse.message
            )
        }
#endif
        let request = DigestTriggerRequest(period: period)
        return try await post(path: "/digests/trigger", body: request)
    }
    
    /// Get the status of a running digest job
    /// - Parameter id: The digest ID
    /// - Returns: Status including progress and ETA
    public func getDigestStatus(id: String) async throws -> DigestStatusResponse {
        return try await get(path: "/digests/\(id)/status")
    }
    
    /// Get all articles for a digest with their content
    /// - Parameter id: The digest ID
    /// - Returns: Articles response with full content
    public func getDigestArticles(id: String) async throws -> DigestArticlesResponse {
        return try await get(path: "/digests/\(id)/articles")
    }

    /// Get raw/source HTML for a digest article.
    /// - Parameters:
    ///   - digestId: Digest identifier
    ///   - articleId: Article identifier
    /// - Returns: Source payload containing upstream HTML
    public func getDigestArticleSource(
        digestId: String,
        articleId: String
    ) async throws -> DigestArticleSourceResponse {
        return try await get(path: "/digests/\(digestId)/articles/\(articleId)/source")
    }

    /// Download a digest EPUB file
    /// - Parameter filename: The EPUB filename
    /// - Returns: Raw EPUB data
    public func downloadDigest(filename: String) async throws -> Data {
        return try await getData(path: "/digests/\(filename)")
    }
    
    // MARK: - Schedules
    
    /// List all schedule configurations
    public func listSchedules() async throws -> [ScheduleResponse] {
#if canImport(EpilogueShared)
        if let sharedHandle {
            let sharedSchedules = try await sharedHandle.client.listSchedules()
            return sharedSchedules.map { schedule in
                ScheduleResponse(
                    id: schedule.id,
                    period: schedule.period,
                    hour: Int(schedule.hour),
                    minute: Int(schedule.minute),
                    enabled: schedule.enabled,
                    timezone: schedule.timezone,
                    nextRunAt: schedule.nextRunAt
                )
            }
        }
#endif
        return try await get(path: "/schedules")
    }
    
    /// Update a schedule configuration
    /// - Parameters:
    ///   - period: The period to update ("morning", "noon", "evening")
    ///   - request: The update request
    /// - Returns: Updated schedule
    public func updateSchedule(period: String, request: ScheduleUpdateRequest) async throws -> ScheduleResponse {
#if canImport(EpilogueShared)
        if let sharedHandle {
            let sharedRequest = EpilogueShared.ScheduleUpdateRequest(
                hour: request.hour.map { KotlinInt(int: Int32($0)) },
                minute: request.minute.map { KotlinInt(int: Int32($0)) },
                enabled: request.enabled.map { KotlinBoolean(bool: $0) },
                timezone: request.timezone
            )
            let schedule = try await sharedHandle.client.updateSchedule(
                period: period.lowercased(),
                request: sharedRequest
            )
            return ScheduleResponse(
                id: schedule.id,
                period: schedule.period,
                hour: Int(schedule.hour),
                minute: Int(schedule.minute),
                enabled: schedule.enabled,
                timezone: schedule.timezone,
                nextRunAt: schedule.nextRunAt
            )
        }
#endif
        return try await put(path: "/schedules/\(period.lowercased())", body: request)
    }
    
    // MARK: - Client Activity
    
    /// Send a heartbeat to indicate the app is active
    public func sendHeartbeat() async throws -> HeartbeatResponse {
        return try await post(path: "/client/heartbeat", body: EmptyRequest())
    }
    
    /// Get client status including activity tracking info
    public func getClientStatus() async throws -> ClientStatusResponse {
#if canImport(EpilogueShared)
        if let sharedHandle {
            let sharedResponse = try await sharedHandle.client.getClientStatus()
            return ClientStatusResponse(
                lastHeartbeatAt: sharedResponse.lastHeartbeatAt,
                lastDownloadAt: sharedResponse.lastDownloadAt,
                lastFeedSyncAt: sharedResponse.lastFeedSyncAt,
                autoDisableEnabled: sharedResponse.autoDisableEnabled,
                autoDisableAfterDays: Int(sharedResponse.autoDisableAfterDays),
                schedulesAutoDisabled: sharedResponse.schedulesAutoDisabled,
                autoDisabledAt: sharedResponse.autoDisabledAt,
                daysUntilAutoDisable: sharedResponse.daysUntilAutoDisable.map { Int(truncating: $0) }
            )
        }
#endif
        return try await get(path: "/client/status")
    }
    
    // MARK: - Config
    
    /// Get the shared client configuration
    public func getConfig() async throws -> ClientConfigResponse {
#if canImport(EpilogueShared)
        if let sharedHandle {
            let sharedResponse = try await sharedHandle.client.getConfig()
            return ClientConfigResponse(
                minWordCount: sharedResponse.minWordCount.map { Int(truncating: $0) },
                morningHour: sharedResponse.morningHour.map { Int(truncating: $0) },
                morningMinute: sharedResponse.morningMinute.map { Int(truncating: $0) },
                noonHour: sharedResponse.noonHour.map { Int(truncating: $0) },
                noonMinute: sharedResponse.noonMinute.map { Int(truncating: $0) },
                eveningHour: sharedResponse.eveningHour.map { Int(truncating: $0) },
                eveningMinute: sharedResponse.eveningMinute.map { Int(truncating: $0) },
                timezone: sharedResponse.timezone,
                aiProvider: nil,
                aiModel: nil,
                scheduleMorning: sharedResponse.scheduleMorning,
                scheduleNoon: sharedResponse.scheduleNoon,
                scheduleEvening: sharedResponse.scheduleEvening,
                whisperProvider: sharedResponse.whisperProvider,
                whisperModel: sharedResponse.whisperModel,
                whisperTimeoutMinutes: sharedResponse.whisperTimeoutMinutes.map { Int(truncating: $0) },
                mediaProcessingIntervalHours: sharedResponse.mediaProcessingIntervalHours.map { Int(truncating: $0) },
                includePodcastsInDigest: sharedResponse.includePodcastsInDigest?.boolValue,
                includeYoutubeInDigest: sharedResponse.includeYoutubeInDigest?.boolValue,
                coverEnabled: sharedResponse.coverEnabled?.boolValue,
                coverProvider: sharedResponse.coverProvider,
                coverQuality: sharedResponse.coverQuality,
                coverPrompt: sharedResponse.coverPrompt,
                coverOverlayEnabled: sharedResponse.coverOverlayEnabled?.boolValue,
                coverOpenAIAPIKey: sharedResponse.coverOpenAiApiKey,
                coverGeminiAPIKey: sharedResponse.coverGeminiApiKey,
                updatedAt: sharedResponse.updatedAt,
                wallabag: sharedResponse.wallabag.map { IntegrationStatus(enabled: $0.enabled, label: $0.label) },
                newsletters: sharedResponse.newsletters.map { IntegrationStatus(enabled: $0.enabled, label: $0.label) }
            )
        }
#endif
        return try await get(path: "/config")
    }
    
    /// Update the shared client configuration
    /// - Parameter request: The configuration update request
    /// - Returns: Updated configuration
    public func updateConfig(_ request: ClientConfigUpdateRequest) async throws -> ClientConfigResponse {
        return try await put(path: "/config", body: request)
    }

    // MARK: - Integrations

    /// Preview Wallabag items without marking them as read.
    public func previewWallabag() async throws -> PreviewResponse {
        return try await post(path: "/config/wallabag/preview", body: EmptyRequest())
    }

    /// Preview newsletter items without marking them as read.
    public func previewNewsletters() async throws -> PreviewResponse {
        return try await post(path: "/newsletters/preview", body: EmptyRequest())
    }

    /// Clear seen markers for Wallabag synthetic feed.
    public func clearWallabagSeen() async throws -> ClearSeenResponse {
        return try await post(path: "/config/wallabag/clear-seen", body: EmptyRequest())
    }

    /// Clear seen markers for newsletters synthetic feed.
    public func clearNewsletterSeen() async throws -> ClearSeenResponse {
        return try await post(path: "/config/newsletters/clear-seen", body: EmptyRequest())
    }

    /// Build the browser URL used to start newsletter OAuth.
    public func newsletterOAuthStartURL() -> URL {
        baseURL.appendingPathComponent("newsletters/oauth/start")
    }

    // MARK: - Media

    /// List configured podcast feeds.
    public func getPodcastFeeds() async throws -> [MediaFeedResponse] {
        return try await get(path: "/media/podcasts")
    }

    /// Create a podcast feed.
    public func createPodcastFeed(_ request: MediaFeedCreateRequest) async throws -> MediaFeedResponse {
        return try await post(path: "/media/podcasts", body: request)
    }

    /// Update a podcast feed.
    public func updatePodcastFeed(
        feedId: String,
        request: MediaFeedUpdateRequest
    ) async throws -> MediaFeedResponse {
        return try await put(path: "/media/podcasts/\(feedId)", body: request)
    }

    /// Delete a podcast feed.
    public func deletePodcastFeed(feedId: String) async throws -> StatusMessageResponse {
        return try await delete(path: "/media/podcasts/\(feedId)")
    }

    /// List configured YouTube feeds.
    public func getYouTubeFeeds() async throws -> [MediaFeedResponse] {
        return try await get(path: "/media/youtube")
    }

    /// Resolve a YouTube channel URL to RSS feed URL.
    public func resolveYouTubeFeed(url: String) async throws -> YouTubeResolveResponse {
        return try await post(path: "/media/youtube/resolve", body: YouTubeResolveRequest(url: url))
    }

    /// Create a YouTube feed.
    public func createYouTubeFeed(_ request: MediaFeedCreateRequest) async throws -> MediaFeedResponse {
        return try await post(path: "/media/youtube", body: request)
    }

    /// Update a YouTube feed.
    public func updateYouTubeFeed(
        feedId: String,
        request: MediaFeedUpdateRequest
    ) async throws -> MediaFeedResponse {
        return try await put(path: "/media/youtube/\(feedId)", body: request)
    }

    /// Delete a YouTube feed.
    public func deleteYouTubeFeed(feedId: String) async throws -> StatusMessageResponse {
        return try await delete(path: "/media/youtube/\(feedId)")
    }

    /// List all podcast items (summary view).
    public func getAllPodcastItems() async throws -> [MediaItemSummaryResponse] {
        return try await get(path: "/media/podcasts/items/all")
    }

    /// List all YouTube items (summary view).
    public func getAllYouTubeItems() async throws -> [MediaItemSummaryResponse] {
        return try await get(path: "/media/youtube/items/all")
    }

    /// Fetch a full media item by ID including transcript/content.
    public func getMediaItem(id: String) async throws -> MediaItemResponse {
        return try await get(path: "/media/items/\(id)")
    }

    /// Get media processing status.
    public func getMediaProcessingStatus() async throws -> MediaProcessingStatusResponse {
        return try await get(path: "/media/status")
    }

    /// Trigger media processing pipeline.
    public func triggerMediaProcessing() async throws -> MediaTriggerResponse {
        return try await post(path: "/media/trigger", body: EmptyRequest())
    }

    // MARK: - Logs

    /// List available server log files.
    public func getLogFiles() async throws -> [LogFileInfoResponse] {
        return try await get(path: "/logs")
    }

    // MARK: - Auth Tokens

    /// List auth API tokens for current user (JWT required).
    public func listAuthTokens() async throws -> [AuthAPITokenResponse] {
        return try await get(path: "/auth/tokens")
    }

    /// Create a new auth API token (JWT required).
    public func createAuthToken(name: String) async throws -> AuthAPITokenCreateResponse {
        return try await post(path: "/auth/tokens", body: AuthAPITokenCreateRequest(name: name))
    }

    /// Revoke an auth API token (JWT required).
    public func revokeAuthToken(id: String) async throws -> StatusMessageResponse {
        return try await delete(path: "/auth/tokens/\(id)")
    }
    
    // MARK: - Private Helpers
    
    private func buildURL(path: String, queryItems: [URLQueryItem] = []) throws -> URL {
        var components = URLComponents(url: baseURL.appendingPathComponent(path), resolvingAgainstBaseURL: true)
        
        if !queryItems.isEmpty {
            components?.queryItems = queryItems
        }
        
        guard let url = components?.url else {
            throw GhostwriterError.invalidURL(path)
        }
        
        return url
    }
    
    private func buildRequest(
        url: URL,
        method: String,
        body: Data? = nil,
        authenticated: Bool = true
    ) -> URLRequest {
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        
        if authenticated, let apiKey = apiKey {
            request.setValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization")
        }
        
        if let body = body {
            request.httpBody = body
        }
        
        return request
    }
    
    private func performRequest<T: Decodable>(_ request: URLRequest) async throws -> T {
        let start = ContinuousClock.now
        let (data, response) = try await session.data(for: request)
        let elapsed = ContinuousClock.now - start
        
        guard let httpResponse = response as? HTTPURLResponse else {
            throw GhostwriterError.networkError(URLError(.badServerResponse))
        }
        
        let ms = Double(elapsed.components.seconds) * 1000.0 + Double(elapsed.components.attoseconds) / 1_000_000_000_000_000.0
        let path = request.url?.path ?? "?"
        perfLogger.debug("\(request.httpMethod ?? "GET") \(path) → \(httpResponse.statusCode) | \(data.count) bytes | \(String(format: "%.1f", ms))ms")
        
        try handleHTTPStatus(httpResponse, data: data)
        
        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            throw GhostwriterError.decodingError(error)
        }
    }
    
    private func handleHTTPStatus(_ response: HTTPURLResponse, data: Data) throws {
        switch response.statusCode {
        case 200..<300:
            return // Success
        case 401:
            throw GhostwriterError.unauthorized
        case 429:
            throw GhostwriterError.rateLimited
        case 404:
            let message = String(data: data, encoding: .utf8)
            throw GhostwriterError.notFound(message ?? "Resource not found")
        case 409:
            let message = String(data: data, encoding: .utf8) ?? "Conflict"
            if message.contains("digest") || message.contains("already") {
                throw GhostwriterError.digestInProgress
            }
            throw GhostwriterError.conflict(message: message)
        default:
            let message = String(data: data, encoding: .utf8)
            throw GhostwriterError.httpError(statusCode: response.statusCode, message: message)
        }
    }
    
    // MARK: - HTTP Methods
    
    private func get<T: Decodable>(
        path: String,
        queryItems: [URLQueryItem] = [],
        authenticated: Bool = true
    ) async throws -> T {
        let url = try buildURL(path: path, queryItems: queryItems)
        let request = buildRequest(url: url, method: "GET", authenticated: authenticated)
        return try await performRequest(request)
    }
    
    private func getData(path: String, authenticated: Bool = true) async throws -> Data {
        let url = try buildURL(path: path)
        let request = buildRequest(url: url, method: "GET", authenticated: authenticated)
        
        let start = ContinuousClock.now
        let (data, response) = try await session.data(for: request)
        let elapsed = ContinuousClock.now - start
        
        guard let httpResponse = response as? HTTPURLResponse else {
            throw GhostwriterError.networkError(URLError(.badServerResponse))
        }
        
        let ms = Double(elapsed.components.seconds) * 1000.0 + Double(elapsed.components.attoseconds) / 1_000_000_000_000_000.0
        perfLogger.debug("GET \(path) → \(httpResponse.statusCode) | \(data.count) bytes | \(String(format: "%.1f", ms))ms")
        
        try handleHTTPStatus(httpResponse, data: data)
        
        return data
    }
    
    private func post<T: Decodable, B: Encodable>(
        path: String,
        body: B,
        authenticated: Bool = true
    ) async throws -> T {
        let url = try buildURL(path: path)
        
        let bodyData: Data
        do {
            bodyData = try encoder.encode(body)
        } catch {
            throw GhostwriterError.encodingError(error)
        }
        
        let request = buildRequest(url: url, method: "POST", body: bodyData, authenticated: authenticated)
        return try await performRequest(request)
    }
    
    private func put<T: Decodable, B: Encodable>(
        path: String,
        body: B,
        authenticated: Bool = true
    ) async throws -> T {
        let url = try buildURL(path: path)
        
        let bodyData: Data
        do {
            bodyData = try encoder.encode(body)
        } catch {
            throw GhostwriterError.encodingError(error)
        }
        
        let request = buildRequest(url: url, method: "PUT", body: bodyData, authenticated: authenticated)
        return try await performRequest(request)
    }
    
    private func delete<T: Decodable>(path: String, authenticated: Bool = true) async throws -> T {
        let url = try buildURL(path: path)
        let request = buildRequest(url: url, method: "DELETE", authenticated: authenticated)
        return try await performRequest(request)
    }
}

// MARK: - Helper Types

private struct EmptyRequest: Encodable {}

private struct EmptyResponse: Decodable {}
