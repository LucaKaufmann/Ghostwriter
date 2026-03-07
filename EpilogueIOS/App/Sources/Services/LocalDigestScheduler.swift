//
//  LocalDigestScheduler.swift
//  Epilogue
//
//  Schedules and runs local digest generation via BGProcessingTask + BGAppRefreshTask.
//  When Ghostwriter is enabled, local scheduling is skipped.
//
//  Multi-layer background strategy:
//    Layer 1 (GUARANTEED):  App launch catch-up
//    Layer 2 (LIKELY):      Local notification reminders
//    Layer 3 (BEST-EFFORT): BGAppRefreshTask for feed pre-fetching
//    Layer 4 (BEST-EFFORT): BGProcessingTask for overnight digest generation
//

import Foundation
import BackgroundTasks
import UserNotifications
import OSLog
import Domain
import Data
import ContentProcessing
import EPUBGeneration
import AIServices

// MARK: - TaskCompletionGuard

/// Ensures BGTask.setTaskCompleted is called exactly once, preventing undefined behavior
/// from double-complete bugs (e.g., expiration handler racing with success path).
actor TaskCompletionGuard {
    private var completed = false

    func complete(_ task: BGTask, success: Bool) {
        guard !completed else { return }
        completed = true
        task.setTaskCompleted(success: success)
    }
}

/// Prevents duplicate execution of the same async operation.
actor AsyncExecutionGate {
    private var isRunning = false

    func runIfIdle(_ operation: @Sendable () async -> Void) async {
        guard !isRunning else { return }
        isRunning = true
        defer { isRunning = false }
        await operation()
    }
}

/// Prevents overlapping scheduled digest generations (e.g. foreground catch-up
/// racing with a BGProcessing handler).
actor DigestGenerationGate {
    private var inProgress = false

    func tryStart() -> Bool {
        guard !inProgress else { return false }
        inProgress = true
        return true
    }

    func finish() {
        inProgress = false
    }
}

// MARK: - LocalDigestScheduler

public final class LocalDigestScheduler: Sendable {
    public static let digestTaskIdentifier = "com.codable.epilogue.digestgeneration"
    public static let feedRefreshTaskIdentifier = "com.codable.epilogue.feedRefresh"
    static let scheduledGenerationLeadTime: TimeInterval = 2 * 60 * 60

    private let feedRepository: FeedRepositoryProtocol
    private let digestRepository: DigestRepositoryProtocol
    private let settingsRepository: SettingsRepositoryProtocol
    private let generationGate = DigestGenerationGate()
    private let logger = Logger(subsystem: "com.epilogue", category: "LocalScheduler")
    private let catchUpGate = AsyncExecutionGate()

    public init(
        feedRepository: FeedRepositoryProtocol,
        digestRepository: DigestRepositoryProtocol,
        settingsRepository: SettingsRepositoryProtocol
    ) {
        self.feedRepository = feedRepository
        self.digestRepository = digestRepository
        self.settingsRepository = settingsRepository
    }

    // MARK: - Registration

    /// Register all background task handlers. Must be called at app launch (before scene setup).
    public func registerBackgroundTasks() {
        BGTaskScheduler.shared.register(
            forTaskWithIdentifier: Self.digestTaskIdentifier,
            using: nil
        ) { [self] task in
            Task {
                await self.handleOvernightDigestTask(task as! BGProcessingTask)
            }
        }

        BGTaskScheduler.shared.register(
            forTaskWithIdentifier: Self.feedRefreshTaskIdentifier,
            using: nil
        ) { [self] task in
            Task {
                await self.handleFeedRefreshTask(task as! BGAppRefreshTask)
            }
        }

        logger.info("Registered local digest + feed refresh background tasks")
    }

    // MARK: - Scheduling

    /// Schedule overnight digest generation (BGProcessingTask).
    /// Targets 2 hours before the next enabled period, requires charging + network.
    public func scheduleOvernightDigest() async {
        BGTaskScheduler.shared.cancel(taskRequestWithIdentifier: Self.digestTaskIdentifier)

        do {
            let ghostwriterEnabled = try await settingsRepository.isGhostwriterEnabled()
            if ghostwriterEnabled {
                logger.info("Ghostwriter enabled — skipping overnight digest schedule")
                return
            }

            let enabledPeriods = try await settingsRepository.getEnabledPeriods()
            guard !enabledPeriods.isEmpty else {
                logger.info("No periods enabled — skipping overnight digest schedule")
                return
            }

            let now = Date()
            guard let nextDigestTime = nextScheduledDigestTime(from: now, periods: enabledPeriods) else {
                logger.warning("Could not compute next digest window — skipping overnight schedule")
                return
            }

            let request = BGProcessingTaskRequest(identifier: Self.digestTaskIdentifier)
            // 2 hours before the next digest window to give iOS scheduling room
            let desiredBegin = nextDigestTime.addingTimeInterval(-2 * 3600)
            request.earliestBeginDate = max(desiredBegin, now.addingTimeInterval(60))
            request.requiresNetworkConnectivity = true
            request.requiresExternalPower = true

            try BGTaskScheduler.shared.submit(request)
            logger.info(
                "Scheduled overnight digest generation: next window \(nextDigestTime), earliest begin \(request.earliestBeginDate ?? nextDigestTime)"
            )
        } catch {
            logger.error("Failed to schedule overnight digest: \(error.localizedDescription)")
        }
    }

    /// Schedule feed pre-fetch (BGAppRefreshTask, ~30s budget).
    /// Runs every ~1 hour to keep feeds fresh for quick digest generation.
    public func scheduleFeedRefresh() {
        BGTaskScheduler.shared.cancel(taskRequestWithIdentifier: Self.feedRefreshTaskIdentifier)

        let request = BGAppRefreshTaskRequest(identifier: Self.feedRefreshTaskIdentifier)
        request.earliestBeginDate = Date(timeIntervalSinceNow: 60 * 60) // 1 hour

        do {
            try BGTaskScheduler.shared.submit(request)
            logger.debug("Scheduled feed refresh background task")
        } catch {
            logger.error("Failed to schedule feed refresh: \(error.localizedDescription)")
        }
    }

    // MARK: - App Launch Catch-Up (PRIMARY — Guaranteed)

    /// Check if a digest was missed and generate it immediately.
    /// This is the MOST RELIABLE layer — runs every time the user opens the app.
    public func checkForMissedDigests() async {
        await catchUpGate.runIfIdle { [self] in
            do {
                let ghostwriterEnabled = try await settingsRepository.isGhostwriterEnabled()
                if ghostwriterEnabled { return }

                let now = Date()
                let calendar = Calendar.current
                let enabledPeriods = try await settingsRepository.getEnabledPeriods()
                guard let latestElapsedPeriod = Self.latestElapsedPeriod(
                    now: now,
                    periods: enabledPeriods,
                    calendar: calendar
                ) else { return }

                let todayStart = calendar.startOfDay(for: now)
                let digestsToday = try await digestRepository.getDigests(from: todayStart, to: now)
                let hasDigestForLatestPeriod = Self.hasDigestCoveringLatestPeriod(
                    latestElapsedPeriod,
                    digests: digestsToday,
                    now: now,
                    calendar: calendar
                )
                guard !hasDigestForLatestPeriod else { return }

                guard let digest = try await withGenerationLock({
                    logger.info("Catch-up: generating missed digest for \(latestElapsedPeriod.rawValue)")
                    let generator = try await buildDigestGenerator()
                    return try await generator.generateDigest(
                        triggerType: .scheduled,
                        period: latestElapsedPeriod.rawValue
                    )
                }) else {
                    logger.info("Catch-up skipped: another scheduled digest generation is already running")
                    return
                }

                logger.info("Catch-up digest complete: \(digest.articleCount) articles")

                await exportIfConfigured(digest: digest)
            } catch {
                logger.error("Catch-up digest generation failed: \(error.localizedDescription)")
            }
        }
    }

    // MARK: - Background Task Handlers

    /// Handle overnight digest generation (BGProcessingTask).
    /// Uses TaskCompletionGuard to prevent double-complete. Cancels work on expiration.
    private func handleOvernightDigestTask(_ task: BGProcessingTask) async {
        logger.info("Overnight digest task started")
        let completionGuard = TaskCompletionGuard()

        // Schedule next overnight run immediately
        await scheduleOvernightDigest()

        let generationTask = Task.detached(priority: .utility) { [self] () async throws -> Bool in
            // Check Ghostwriter
            let ghostwriterEnabled = try await self.settingsRepository.isGhostwriterEnabled()
            if ghostwriterEnabled {
                self.logger.info("Ghostwriter enabled — skipping overnight generation")
                return false
            }

            let enabledPeriods = try await self.settingsRepository.getEnabledPeriods()
            guard !enabledPeriods.isEmpty else {
                self.logger.info("No enabled periods — skipping overnight generation")
                return false
            }

            let now = Date()
            let periodToGenerate = Self.latestElapsedPeriod(now: now, periods: enabledPeriods) ??
                enabledPeriods.min(by: {
                    ($0.hour, $0.minute) < ($1.hour, $1.minute)
                })

            guard let digest = try await self.withGenerationLock({
                let generator = try await self.buildDigestGenerator()
                return try await generator.generateDigest(
                    triggerType: .scheduled,
                    period: periodToGenerate?.rawValue
                )
            }) else {
                self.logger.info("Overnight digest skipped: another scheduled generation is already running")
                return false
            }

            self.logger.info("Overnight digest complete: \(digest.articleCount) articles")
            await self.exportIfConfigured(digest: digest)
            await self.scheduleMorningNotification(for: digest)
            return true
        }

        task.expirationHandler = {
            generationTask.cancel()
            self.logger.warning("Overnight digest task expired")
            Task { await completionGuard.complete(task, success: false) }
        }

        do {
            let generatedDigest = try await generationTask.value
            if generatedDigest {
                await completionGuard.complete(task, success: true)
            } else {
                // Ghostwriter was enabled, no local generation needed
                await completionGuard.complete(task, success: true)
            }
        } catch {
            logger.error("Overnight digest failed: \(error.localizedDescription)")
            await completionGuard.complete(task, success: false)
        }
    }

    /// Handle feed pre-fetch (BGAppRefreshTask, ~30s budget).
    /// Timeboxed to 20s, fetches feeds sorted by least-recently-fetched (round-robin).
    private func handleFeedRefreshTask(_ task: BGAppRefreshTask) async {
        logger.info("Feed refresh task started")
        let completionGuard = TaskCompletionGuard()

        // Schedule next refresh immediately
        scheduleFeedRefresh()

        let fetchTask = Task.detached(priority: .utility) { [self] in
            let deadline = Date(timeIntervalSinceNow: 20) // Stay well under 30s budget
            let feeds = try await self.feedRepository.getEnabledFeeds()

            let feedParser = EpilogueFeedParser()
            var fetchedCount = 0

            for feed in feeds {
                guard Date() < deadline else {
                    self.logger.info("Feed refresh timeboxed after \(fetchedCount) feeds")
                    break
                }
                try Task.checkCancellation()

                do {
                    _ = try await feedParser.parseFeed(url: feed.url, feedName: feed.name)
                    fetchedCount += 1
                } catch {
                    self.logger.warning("Feed refresh failed for \(feed.name): \(error.localizedDescription)")
                }
            }

            self.logger.info("Feed refresh completed: \(fetchedCount) feeds updated")
        }

        task.expirationHandler = {
            fetchTask.cancel()
            self.logger.warning("Feed refresh task expired")
            Task { await completionGuard.complete(task, success: false) }
        }

        do {
            try await fetchTask.value
            await completionGuard.complete(task, success: true)
        } catch {
            logger.error("Feed refresh failed: \(error.localizedDescription)")
            await completionGuard.complete(task, success: false)
        }
    }

    // MARK: - Notifications

    /// Schedule a "Digest Ready" notification for the earliest enabled period.
    /// Called after overnight digest generation succeeds.
    func scheduleMorningNotification(for digest: Digest) async {
        let enabledPeriods = (try? await settingsRepository.getEnabledPeriods()) ?? []
        guard let earliest = enabledPeriods.min(by: {
            ($0.hour, $0.minute) < ($1.hour, $1.minute)
        }) else { return }

        // Remove previous ready notification
        UNUserNotificationCenter.current().removePendingNotificationRequests(
            withIdentifiers: ["digest-ready"]
        )

        let content = UNMutableNotificationContent()
        content.title = "Your Digest is Ready"
        content.body = "\(digest.articleCount) articles from your feeds"
        content.sound = .default
        content.categoryIdentifier = "DIGEST_READY"

        let now = Date()
        var components = Calendar.current.dateComponents([.year, .month, .day], from: now)
        components.hour = earliest.hour
        components.minute = earliest.minute
        components.second = 0

        let scheduledToday = Calendar.current.date(from: components) ?? now
        let fireDate = scheduledToday > now ? scheduledToday : now.addingTimeInterval(60)
        let dateComponents = Calendar.current.dateComponents(
            [.year, .month, .day, .hour, .minute],
            from: fireDate
        )

        let trigger = UNCalendarNotificationTrigger(dateMatching: dateComponents, repeats: false)
        let request = UNNotificationRequest(
            identifier: "digest-ready",
            content: content,
            trigger: trigger
        )

        try? await UNUserNotificationCenter.current().add(request)
        logger.info("Scheduled 'digest ready' notification for \(earliest.hour):\(earliest.minute)")
    }

    /// Schedule a standing daily reminder notification.
    /// Fires daily at the earliest enabled period. Replaced by "digest ready" when overnight succeeds.
    public func scheduleDigestReminderNotification() async {
        let requestID = "daily-digest-reminder"
        UNUserNotificationCenter.current().removePendingNotificationRequests(withIdentifiers: [requestID])

        let enabledPeriods = (try? await settingsRepository.getEnabledPeriods()) ?? []
        guard let earliest = enabledPeriods.min(by: {
            ($0.hour, $0.minute) < ($1.hour, $1.minute)
        }) else {
            logger.info("No enabled periods — removed daily digest reminder")
            return
        }

        let content = UNMutableNotificationContent()
        content.title = "Time for Your Digest"
        content.body = "Tap to generate your reading digest"
        content.sound = .default
        content.categoryIdentifier = "DIGEST_REMINDER"

        var dateComponents = DateComponents()
        dateComponents.hour = earliest.hour
        dateComponents.minute = earliest.minute

        // Repeating daily
        let trigger = UNCalendarNotificationTrigger(dateMatching: dateComponents, repeats: true)
        let request = UNNotificationRequest(
            identifier: requestID,
            content: content,
            trigger: trigger
        )

        try? await UNUserNotificationCenter.current().add(request)
        logger.info("Scheduled daily digest reminder for \(earliest.hour):\(earliest.minute)")
    }

    /// Register notification categories with action buttons.
    public static func registerNotificationCategories() {
        let readAction = UNNotificationAction(
            identifier: "READ_DIGEST",
            title: "Read Now",
            options: [.foreground]
        )

        let generateAction = UNNotificationAction(
            identifier: "GENERATE_DIGEST",
            title: "Generate Now",
            options: [.foreground]
        )

        let readyCategory = UNNotificationCategory(
            identifier: "DIGEST_READY",
            actions: [readAction],
            intentIdentifiers: []
        )

        let reminderCategory = UNNotificationCategory(
            identifier: "DIGEST_REMINDER",
            actions: [generateAction],
            intentIdentifiers: []
        )

        UNUserNotificationCenter.current().setNotificationCategories([readyCategory, reminderCategory])
    }

    /// Remove delivered notifications on app open to keep notification center clean.
    public static func cleanUpDeliveredNotifications() {
        UNUserNotificationCenter.current().removeDeliveredNotifications(
            withIdentifiers: ["digest-ready", "daily-digest-reminder"]
        )
    }

    // MARK: - Helpers

    /// Returns the latest elapsed period today, or nil if no period has elapsed yet.
    static func latestElapsedPeriod(
        now: Date,
        periods: Set<DigestPeriod>,
        calendar: Calendar = .current
    ) -> DigestPeriod? {
        let elapsedPeriods = periods.compactMap { period -> (DigestPeriod, Date)? in
            guard let scheduledTime = scheduledTime(for: period, on: now, calendar: calendar) else {
                return nil
            }
            guard now >= scheduledTime else { return nil }
            return (period, scheduledTime)
        }

        return elapsedPeriods.max(by: { $0.1 < $1.1 })?.0
    }

    /// Returns true if a complete digest (or an in-progress digest) already covers the latest period.
    static func hasDigestCoveringLatestPeriod(
        _ latestPeriod: DigestPeriod,
        digests: [Digest],
        now: Date,
        calendar: Calendar = .current
    ) -> Bool {
        let normalizedLatestPeriod = latestPeriod.rawValue.lowercased()
        let digestsThatCount = digests.filter { digest in
            digest.isComplete || (!digest.isComplete && digest.errorMessage == nil)
        }

        if digestsThatCount.contains(where: { digest in
            digest.period?.lowercased() == normalizedLatestPeriod
        }) {
            return true
        }

        // Backward compatibility for legacy local digests that were saved without period.
        guard let dueTime = scheduledTime(for: latestPeriod, on: now, calendar: calendar) else {
            return false
        }
        let dayStart = calendar.startOfDay(for: now)
        let fallbackWindowStart = max(dayStart, dueTime.addingTimeInterval(-scheduledGenerationLeadTime))
        return digestsThatCount.contains(where: { digest in
            guard digest.generatedAt >= fallbackWindowStart else { return false }
            guard let normalizedPeriod = digest.period?.lowercased() else {
                // Legacy local digests were saved without period.
                return true
            }
            // Manual digests are allowed to satisfy the latest period window.
            return normalizedPeriod == "manual"
        })
    }

    static func scheduledTime(
        for period: DigestPeriod,
        on date: Date,
        calendar: Calendar = .current
    ) -> Date? {
        var components = calendar.dateComponents([.year, .month, .day], from: date)
        components.hour = period.hour
        components.minute = period.minute
        components.second = 0
        return calendar.date(from: components)
    }

    /// Returns the next enabled digest period occurrence from a reference date.
    /// If an enabled period is still ahead today, uses today's window; otherwise tomorrow's earliest.
    private func nextScheduledDigestTime(from now: Date, periods: Set<DigestPeriod>) -> Date? {
        guard !periods.isEmpty else { return nil }

        let calendar = Calendar.current
        let todayCandidates = periods.compactMap { period -> Date? in
            var components = calendar.dateComponents([.year, .month, .day], from: now)
            components.hour = period.hour
            components.minute = period.minute
            components.second = 0
            return calendar.date(from: components)
        }

        if let nextToday = todayCandidates.filter({ $0 >= now }).min() {
            return nextToday
        }

        guard let earliest = periods.min(by: { ($0.hour, $0.minute) < ($1.hour, $1.minute) }) else {
            return nil
        }

        guard let tomorrow = calendar.date(byAdding: .day, value: 1, to: calendar.startOfDay(for: now)) else {
            return nil
        }

        var components = calendar.dateComponents([.year, .month, .day], from: tomorrow)
        components.hour = earliest.hour
        components.minute = earliest.minute
        components.second = 0
        return calendar.date(from: components)
    }

    private func withGenerationLock<T>(_ operation: @Sendable () async throws -> T) async throws -> T? {
        guard await generationGate.tryStart() else { return nil }

        do {
            let result = try await operation()
            await generationGate.finish()
            return result
        } catch {
            await generationGate.finish()
            throw error
        }
    }

    func buildDigestGenerator() async throws -> DigestGenerator {
        let feedParser = EpilogueFeedParser()
        let contentExtractor = ContentExtractor()

        let apiKey = try await settingsRepository.getOpenAIKey()
        let aiService: AIServiceProtocol?
        if let key = apiKey, !key.isEmpty {
            aiService = OpenAIService(apiKey: key)
        } else {
            aiService = nil
        }

        let minWordCount = try await settingsRepository.getMinWordCount()
        let articleRepository = ArticleRepository(
            feedParser: feedParser,
            contentExtractor: contentExtractor,
            aiService: aiService,
            minWordCount: minWordCount
        )

        return DigestGenerator(
            feedRepository: feedRepository,
            digestRepository: digestRepository,
            articleRepository: articleRepository,
            epubBuilder: EPUBBuilder()
        )
    }

    private func exportIfConfigured(digest: Digest) async {
        await CustomExportHelper.exportIfConfigured(
            fileURL: URL(fileURLWithPath: digest.epubFilePath),
            settingsRepository: settingsRepository
        )
    }
}
