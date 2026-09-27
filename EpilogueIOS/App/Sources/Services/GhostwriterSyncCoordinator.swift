//
//  GhostwriterSyncCoordinator.swift
//  Epilogue
//
//  Created on 2026-01-26.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import Foundation
import Domain
import Data
import GhostwriterClient
import OSLog
import SwiftData

enum SyncComponent: String {
    case configuration, feed, digest, schedule, combined, settings
}

struct SyncIssue {
    let component: SyncComponent
    let phase: String
    let error: Error
}

struct SyncRunError: LocalizedError {
    let issues: [SyncIssue]

    var errorDescription: String? {
        issues.map { "\($0.component.rawValue) \($0.phase): \($0.error.localizedDescription)" }
            .joined(separator: "; ")
    }

    var hasFeedUpgrade: Bool {
        issues.contains { issue in
            if case .some(.upgradeRequired) = issue.error as? FeedSyncV2Error { return true }
            return false
        }
    }

    var hasFeedServerChange: Bool {
        issues.contains { issue in
            if case .some(.serverChanged) = issue.error as? FeedSyncV2Error { return true }
            return false
        }
    }
}

/// Internal seam for the coordinator's asynchronous effects. Production uses the existing services.
struct SyncOperations {
    var configured: @MainActor () async throws -> Bool
    var lastDigestSync: @MainActor () async throws -> Date?
    var feedSince: @MainActor () async throws -> Date?
    var heartbeat: @MainActor () async throws -> Void
    var feed: @MainActor (SyncPerformanceTracker?) async throws -> Void
    var fetchCombined: @MainActor (Date?, [String]) async throws -> SyncResponse
    var fetchSchedules: @MainActor () async throws -> [ScheduleResponse]
    var applyConfig: @MainActor (ClientConfigResponse) async throws -> Void
    var syncConfig: @MainActor () async throws -> Bool
    var knownDigestIDs: @MainActor () async throws -> [String]
    var applyDigests: @MainActor ([SyncDigest], SyncPerformanceTracker?) async throws -> Void
    var syncDigests: @MainActor (SyncPerformanceTracker?) async throws -> Void
    var saveEnabledPeriods: @MainActor (Set<DigestPeriod>) async throws -> Void
    var saveScheduleTimes: @MainActor (ScheduleTimeValues) async throws -> Void
}

struct ScheduleTimeValues {
    let morningHour: Int
    let morningMinute: Int
    let noonHour: Int
    let noonMinute: Int
    let eveningHour: Int
    let eveningMinute: Int
    let timezone: String
}

/// Coordinates all Ghostwriter sync operations
///
/// This is the main entry point for syncing with Ghostwriter.
/// Call `performFullSync()` on app launch or when the user triggers a sync.
@MainActor
public final class GhostwriterSyncCoordinator: ObservableObject {
    private let feedSyncService: FeedSyncService
    private let digestSyncService: DigestSyncService
    private let configSyncManager: ConfigSyncManager
    private let heartbeatService: HeartbeatService
    private let settingsRepository: SettingsRepositoryProtocol
    var operations: SyncOperations
    var now: () -> Date
    private let logger = Logger(subsystem: "com.epilogue", category: "GhostwriterSync")

    @Published public private(set) var isSyncing = false
    @Published public private(set) var lastSyncError: Error?
    @Published public private(set) var lastSyncTime: Date?

    public convenience init(
        settingsRepository: SettingsRepositoryProtocol,
        feedRepository: FeedRepositoryProtocol,
        digestRepository: DigestRepositoryProtocol,
        modelContainer: ModelContainer
    ) {
        self.init(settingsRepository: settingsRepository, feedRepository: feedRepository,
                  digestRepository: digestRepository, modelContainer: modelContainer,
                  operations: nil, now: Date.init)
    }

    init(
        settingsRepository: SettingsRepositoryProtocol,
        feedRepository: FeedRepositoryProtocol,
        digestRepository: DigestRepositoryProtocol,
        modelContainer: ModelContainer,
        operations injectedOperations: SyncOperations?,
        now: @escaping () -> Date
    ) {
        self.settingsRepository = settingsRepository
        self.now = now

        self.feedSyncService = FeedSyncService(
            settingsRepository: settingsRepository,
            modelContainer: modelContainer
        )

        self.digestSyncService = DigestSyncService(
            settingsRepository: settingsRepository,
            digestRepository: digestRepository
        )

        self.configSyncManager = ConfigSyncManager(
            settingsRepository: settingsRepository
        )

        self.heartbeatService = HeartbeatService(
            settingsRepository: settingsRepository
        )

        let feed = self.feedSyncService
        let digest = self.digestSyncService
        let config = self.configSyncManager
        let heartbeat = self.heartbeatService
        let makeClient: @MainActor () async throws -> GhostwriterClient = {
            guard let url = try await settingsRepository.getGhostwriterURL() else {
                throw GhostwriterError.notConfigured
            }
            let apiKey = try await settingsRepository.getGhostwriterAPIKey()
            return try GhostwriterClient(baseURLString: url, apiKey: apiKey)
        }
        self.operations = injectedOperations ?? SyncOperations(
            configured: { try await settingsRepository.isGhostwriterConfigured() },
            lastDigestSync: { try await settingsRepository.getLastDigestSyncTime() },
            feedSince: { try await settingsRepository.getLastFeedSyncTime() },
            heartbeat: { _ = try await heartbeat.sendHeartbeat() },
            feed: { try await feed.sync(tracker: $0) },
            fetchCombined: { since, ids in
                let client = try await makeClient()
                return try await client.performSync(feedSince: since, knownDigestIds: ids)
            },
            fetchSchedules: {
                let client = try await makeClient()
                return try await client.listSchedules()
            },
            applyConfig: { try await config.applyPreFetchedConfig($0) },
            syncConfig: { try await config.sync() },
            knownDigestIDs: { try await digest.getKnownRemoteIds() },
            applyDigests: { try await digest.processDigestsFromSync($0, tracker: $1) },
            syncDigests: { try await digest.sync(tracker: $0) },
            saveEnabledPeriods: { try await settingsRepository.setEnabledPeriods($0) },
            saveScheduleTimes: { times in
                try await settingsRepository.setGhostwriterSchedule(
                    morningHour: times.morningHour, morningMinute: times.morningMinute,
                    noonHour: times.noonHour, noonMinute: times.noonMinute,
                    eveningHour: times.eveningHour, eveningMinute: times.eveningMinute,
                    timezone: times.timezone
                )
            }
        )
    }

    // MARK: - Public API

    /// Check if Ghostwriter is configured
    public func isConfigured() async -> Bool {
        do {
            return try await settingsRepository.isGhostwriterConfigured()
        } catch {
            return false
        }
    }

    /// Minimum interval between digest syncs (1 hour)
    private static let digestSyncInterval: TimeInterval = 3600

    /// Perform a full sync with Ghostwriter.
    public func performFullSync() async {
        await run(forceDigests: false)
    }

    /// Force a full sync including digests regardless of timing.
    public func performFullSyncIncludingDigests() async {
        await run(forceDigests: true)
    }

    var requiresOlderServerFeedPreview: Bool {
        if let error = lastSyncError as? SyncRunError { return error.hasFeedUpgrade }
        if case .some(.upgradeRequired) = lastSyncError as? FeedSyncV2Error { return true }
        return false
    }

    var requiresNewFeedBinding: Bool {
        if let error = lastSyncError as? SyncRunError { return error.hasFeedServerChange }
        if case .some(.serverChanged) = lastSyncError as? FeedSyncV2Error { return true }
        return false
    }

    private func run(forceDigests: Bool) async {
        guard !isSyncing else { return }
        isSyncing = true
        lastSyncError = nil
        let tracker = SyncPerformanceTracker()
        defer {
            tracker.logSummary()
            isSyncing = false
        }

        do {
            let configured: Bool
            do {
                configured = try await operations.configured()
                try Task.checkCancellation()
            } catch {
                try rethrowCancellation(error)
                lastSyncError = SyncRunError(issues: [SyncIssue(component: .settings,
                                                                phase: "configuration read", error: error)])
                return
            }
            guard configured else {
                logger.debug("Ghostwriter not configured, skipping sync")
                return
            }

            var issues: [SyncIssue] = []
            do {
                try await operations.heartbeat()
                try Task.checkCancellation()
            } catch {
                try rethrowCancellation(error)
                logger.warning("Heartbeat failed: \(error.localizedDescription)")
            }
            do {
                try await operations.feed(tracker)
                try Task.checkCancellation()
            } catch {
                try record(error, component: .feed, phase: "v2", into: &issues)
            }

            let shouldSyncDigests: Bool
            if forceDigests {
                shouldSyncDigests = true
            } else {
                do {
                    let lastDigestSync = try await operations.lastDigestSync()
                    try Task.checkCancellation()
                    shouldSyncDigests = lastDigestSync.map {
                        now().timeIntervalSince($0) >= Self.digestSyncInterval
                    } ?? true
                } catch {
                    try record(error, component: .settings, phase: "digest cadence read", into: &issues)
                    shouldSyncDigests = false
                }
            }

            let feedSince: Date?
            let knownDigestIDs: [String]
            do {
                feedSince = try await operations.feedSince()
                try Task.checkCancellation()
                knownDigestIDs = try await operations.knownDigestIDs()
                try Task.checkCancellation()
            } catch {
                try record(error, component: .settings, phase: "combined request input", into: &issues)
                finish(issues)
                return
            }

            let response: SyncResponse
            do {
                response = try await operations.fetchCombined(feedSince, knownDigestIDs)
                try Task.checkCancellation()
            } catch {
                try rethrowCancellation(error)
                logger.warning("Combined sync fetch failed: \(error.localizedDescription)")
                let fallbackIssues = try await runFallback(syncDigests: shouldSyncDigests,
                                                           tracker: tracker)
                if !fallbackIssues.isEmpty {
                    issues.append(SyncIssue(component: .combined,
                                            phase: combinedFetchPhase(error), error: error))
                    issues.append(contentsOf: fallbackIssues)
                }
                finish(issues)
                return
            }

            issues.append(contentsOf: try await applyCombined(response,
                                                               syncDigests: shouldSyncDigests,
                                                               tracker: tracker))
            finish(issues)
        } catch {
            logger.warning("Ghostwriter sync stopped: \(error.localizedDescription)")
            lastSyncError = error
        }
    }

    private func finish(_ issues: [SyncIssue]) {
        if issues.isEmpty {
            lastSyncTime = now()
            logger.info("Ghostwriter sync completed successfully")
        } else {
            lastSyncError = SyncRunError(issues: issues)
            logger.warning("Ghostwriter sync completed with \(issues.count) issue(s)")
        }
    }

    private func record(_ error: Error, component: SyncComponent, phase: String,
                        into issues: inout [SyncIssue]) throws {
        try rethrowCancellation(error)
        issues.append(SyncIssue(component: component, phase: phase, error: error))
    }

    private func rethrowCancellation(_ error: Error) throws {
        try Task.checkCancellation()
        if error is CancellationError { throw error }
    }

    private func combinedFetchPhase(_ error: Error) -> String {
        if case let .httpError(statusCode, _) = error as? GhostwriterError,
           statusCode == 404 || statusCode == 405 {
            return "unsupported endpoint"
        }
        return "transport"
    }

    private func applyCombined(_ response: SyncResponse, syncDigests: Bool,
                               tracker: SyncPerformanceTracker) async throws -> [SyncIssue] {
        var issues: [SyncIssue] = []
        var configSucceeded = false
        do {
            try await operations.applyConfig(response.config)
            try Task.checkCancellation()
            configSucceeded = true
        } catch {
            try record(error, component: .configuration, phase: "apply", into: &issues)
        }

        // The combined feed section is v1 and must never enter feed v2 state.
        if syncDigests {
            do {
                try await operations.applyDigests(response.digests.newDigests, tracker)
                try Task.checkCancellation()
            } catch {
                try record(error, component: .digest, phase: "ingest", into: &issues)
            }
        }

        if configSucceeded {
            do {
                let schedules = try await operations.fetchSchedules()
                try Task.checkCancellation()
                try await applyScheduleParts(schedules, includeTimes: true, issues: &issues)
            } catch {
                try record(error, component: .schedule, phase: "fetch", into: &issues)
            }
        } else {
            // The combined schedule times predate a pending local config upload.
            try await applyScheduleParts(response.schedules, includeTimes: false, issues: &issues)
        }
        return issues
    }

    private func runFallback(syncDigests: Bool,
                             tracker: SyncPerformanceTracker) async throws -> [SyncIssue] {
        var issues: [SyncIssue] = []
        var configSucceeded = false
        do {
            configSucceeded = try await operations.syncConfig()
            try Task.checkCancellation()
            if !configSucceeded {
                issues.append(SyncIssue(component: .configuration, phase: "fallback",
                                        error: ConfigSyncIncomplete.sync))
            }
        } catch {
            try record(error, component: .configuration, phase: "fallback", into: &issues)
        }

        do {
            let schedules = try await operations.fetchSchedules()
            try Task.checkCancellation()
            try await applyScheduleParts(schedules, includeTimes: configSucceeded, issues: &issues)
        } catch {
            try record(error, component: .schedule, phase: "fallback fetch", into: &issues)
        }

        if syncDigests {
            do {
                try await operations.syncDigests(tracker)
                try Task.checkCancellation()
            } catch {
                try record(error, component: .digest, phase: "fallback", into: &issues)
            }
        }
        return issues
    }

    private func applyScheduleParts(_ schedules: [ScheduleResponse], includeTimes: Bool,
                                    issues: inout [SyncIssue]) async throws {
        do {
            try await applyEnabledPeriods(schedules)
            try Task.checkCancellation()
        } catch {
            try record(error, component: .schedule, phase: "enabled states", into: &issues)
        }
        if includeTimes {
            do {
                try await applyScheduleTimes(schedules)
                try Task.checkCancellation()
            } catch {
                try record(error, component: .schedule, phase: "times", into: &issues)
            }
        }
    }

    /// Sync only feeds
    public func syncFeeds() async throws {
        try await feedSyncService.sync()
    }

    /// Read-only compatibility view for servers that do not support feed v2.
    /// These rows never enter SwiftData, the v2 cursor, or the mutation queue.
    public func previewOlderServerFeeds() async throws -> [FeedResponse] {
        guard let url = try await settingsRepository.getGhostwriterURL() else { return [] }
        let key = try await settingsRepository.getGhostwriterAPIKey()
        let client = try GhostwriterClient(baseURLString: url, apiKey: key)
        return try await client.listFeeds()
    }

    /// Sync only digests
    public func syncDigests() async throws {
        try await digestSyncService.sync()
    }

    /// Trigger a digest generation on the server
    public func triggerDigest(period: String = "manual") async throws -> DigestTriggerResponse {
        return try await digestSyncService.triggerDigest(period: period)
    }

    /// Get the status of a running digest job
    public func getDigestStatus(digestId: String) async throws -> DigestStatusResponse {
        return try await digestSyncService.getDigestStatus(digestId: digestId)
    }

    /// Download an EPUB for an already-synced digest.
    public func downloadDigestEpub(remoteId: String, filenameHint: String? = nil) async throws -> URL {
        return try await digestSyncService.downloadDigestEpub(
            remoteId: remoteId,
            filenameHint: filenameHint
        )
    }

    /// Download a PDF for an already-synced digest.
    public func downloadDigestPdf(remoteId: String, filenameHint: String? = nil) async throws -> URL {
        return try await digestSyncService.downloadDigestPdf(
            remoteId: remoteId,
            filenameHint: filenameHint
        )
    }

    public func addOrEditFeed(url: String, title: String, mode: ProcessingMode,
                              isEnabled: Bool, maxArticles: Int) throws {
        try feedSyncService.addOrEdit(url: url, title: title, mode: mode,
                                      isEnabled: isEnabled, maxArticles: maxArticles)
    }

    public func deleteFeed(url: String) throws {
        try feedSyncService.delete(url: url)
    }

    public func startNewFeedBinding() throws {
        try feedSyncService.startNewBinding()
    }

    func resolvePreviousFeedProposal(opId: String,
                                     action: IOSFeedV2StoreEngine.PreviousProposalAction) throws {
        try feedSyncService.resolvePrevious(opId: opId, action: action)
    }

    public func suspendFeedBindingForDestinationChange(_ url: String?) throws {
        try feedSyncService.suspendForDestinationChange(url)
    }

    func resolveFeed(opId: String, action: IOSFeedV2StoreEngine.Resolution,
                     correctedTitle: String? = nil) throws {
        try feedSyncService.resolve(opId: opId, action: action,
                                    correctedTitle: correctedTitle)
    }

    /// Push schedule enable/disable state to the server.
    public func updateSchedule(period: DigestPeriod, enabled: Bool) async throws {
        try await configSyncManager.updateSchedule(period: period, enabled: enabled)
    }

    /// Push min_word_count to the server.
    public func pushMinWordCount(_ count: Int) async throws {
        try await configSyncManager.pushMinWordCount(count)
    }

    /// Check server health
    public func checkServerHealth() async throws -> HealthResponse {
        return try await heartbeatService.checkHealth()
    }

    /// Get client status from server
    public func getClientStatus() async throws -> ClientStatusResponse {
        return try await heartbeatService.getClientStatus()
    }

    /// Returns whether PDF digest downloads are enabled on the server.
    public func isPdfDownloadEnabled() async -> Bool {
        do {
            guard let url = try await settingsRepository.getGhostwriterURL() else { return false }
            let apiKey = try await settingsRepository.getGhostwriterAPIKey()
            let client = try GhostwriterClient(baseURLString: url, apiKey: apiKey)
            let config = try await client.getConfig()
            return config.pdfEnabled == true
        } catch {
            logger.warning("Failed to load PDF setting from server: \(error.localizedDescription)")
            return false
        }
    }

    // MARK: - Schedule Sync

    private func applyEnabledPeriods(_ schedules: [ScheduleResponse]) async throws {
        var enabledPeriods: Set<DigestPeriod> = []
        for schedule in schedules where schedule.enabled {
            switch schedule.period.lowercased() {
            case "morning": enabledPeriods.insert(.morning)
            case "noon": enabledPeriods.insert(.noon)
            case "evening": enabledPeriods.insert(.evening)
            default: break
            }
        }
        try await operations.saveEnabledPeriods(enabledPeriods)
    }

    private func applyScheduleTimes(_ schedules: [ScheduleResponse]) async throws {
        var morningHour = 7, morningMinute = 0
        var noonHour = 12, noonMinute = 0
        var eveningHour = 18, eveningMinute = 0
        var timezone = "UTC"

        for schedule in schedules {
            let period: DigestPeriod?
            switch schedule.period.lowercased() {
            case "morning": period = .morning
            case "noon": period = .noon
            case "evening": period = .evening
            default: period = nil
            }

            guard let period else { continue }

            switch period {
            case .morning:
                morningHour = schedule.hour
                morningMinute = schedule.minute
            case .noon:
                noonHour = schedule.hour
                noonMinute = schedule.minute
            case .evening:
                eveningHour = schedule.hour
                eveningMinute = schedule.minute
            }
            timezone = schedule.timezone
        }

        try await operations.saveScheduleTimes(ScheduleTimeValues(
            morningHour: morningHour, morningMinute: morningMinute,
            noonHour: noonHour, noonMinute: noonMinute,
            eveningHour: eveningHour, eveningMinute: eveningMinute,
            timezone: timezone
        ))

        logger.info("Applied refreshed schedule times")
    }
}
