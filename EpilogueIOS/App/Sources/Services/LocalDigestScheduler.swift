//
//  LocalDigestScheduler.swift
//  Epilogue
//
//  Schedules and runs local digest generation via BGProcessingTask.
//  When Ghostwriter is enabled, local scheduling is skipped.
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

@MainActor
public final class LocalDigestScheduler {
    public static let taskIdentifier = "com.epilogue.app.digestgeneration"

    private let feedRepository: FeedRepositoryProtocol
    private let digestRepository: DigestRepositoryProtocol
    private let settingsRepository: SettingsRepositoryProtocol
    private let logger = Logger(subsystem: "com.epilogue", category: "LocalScheduler")

    public init(
        feedRepository: FeedRepositoryProtocol,
        digestRepository: DigestRepositoryProtocol,
        settingsRepository: SettingsRepositoryProtocol
    ) {
        self.feedRepository = feedRepository
        self.digestRepository = digestRepository
        self.settingsRepository = settingsRepository
    }

    /// Register the background task handler. Must be called at app launch (before scene setup).
    nonisolated public func registerBackgroundTask() {
        BGTaskScheduler.shared.register(
            forTaskWithIdentifier: Self.taskIdentifier,
            using: nil
        ) { task in
            Task { @MainActor in
                await self.handleBackgroundTask(task as! BGProcessingTask)
            }
        }
        logger.info("Registered local digest background task")
    }

    /// Schedule the next background digest run based on enabled periods.
    public func scheduleNextDigest() async {
        // Cancel existing
        BGTaskScheduler.shared.cancel(taskRequestWithIdentifier: Self.taskIdentifier)

        do {
            // Skip if Ghostwriter is enabled
            let ghostwriterEnabled = try await settingsRepository.isGhostwriterEnabled()
            if ghostwriterEnabled {
                logger.info("Ghostwriter enabled — skipping local schedule")
                return
            }

            let enabledPeriods = try await settingsRepository.getEnabledPeriods()
            guard !enabledPeriods.isEmpty else {
                logger.info("No periods enabled — skipping schedule")
                return
            }

            let nextDate = calculateNextRunDate(for: enabledPeriods)
            logger.info("Scheduling next local digest at \(nextDate)")

            let request = BGProcessingTaskRequest(identifier: Self.taskIdentifier)
            request.earliestBeginDate = nextDate
            request.requiresNetworkConnectivity = true
            request.requiresExternalPower = false

            try BGTaskScheduler.shared.submit(request)
            logger.info("Local digest scheduled for \(nextDate)")
        } catch {
            logger.error("Failed to schedule local digest: \(error.localizedDescription)")
        }
    }

    // MARK: - Background Task Handler

    private func handleBackgroundTask(_ task: BGProcessingTask) async {
        logger.info("Background digest task started")

        // Schedule next run immediately
        await scheduleNextDigest()

        task.expirationHandler = {
            self.logger.warning("Background digest task expired")
            task.setTaskCompleted(success: false)
        }

        do {
            // Check Ghostwriter
            let ghostwriterEnabled = try await settingsRepository.isGhostwriterEnabled()
            if ghostwriterEnabled {
                logger.info("Ghostwriter enabled — skipping local generation")
                task.setTaskCompleted(success: true)
                return
            }

            // Build generator
            let generator = try await buildDigestGenerator()
            let digest = try await generator.generateDigest(triggerType: .scheduled)

            logger.info("Background digest complete: \(digest.articleCount) articles")

            // Notify user
            let shouldNotify = try await settingsRepository.shouldShowNotifications()
            if shouldNotify {
                await sendNotification(articleCount: digest.articleCount)
            }

            task.setTaskCompleted(success: true)
        } catch {
            logger.error("Background digest failed: \(error.localizedDescription)")
            task.setTaskCompleted(success: false)
        }
    }

    // MARK: - Helpers

    private func buildDigestGenerator() async throws -> DigestGenerator {
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

    private func calculateNextRunDate(for periods: Set<DigestPeriod>) -> Date {
        let calendar = Calendar.current
        let now = Date()
        var nextDates: [Date] = []

        for period in periods {
            var components = calendar.dateComponents([.year, .month, .day], from: now)
            components.hour = period.hour
            components.minute = period.minute
            components.second = 0

            guard let scheduled = calendar.date(from: components) else { continue }

            if scheduled <= now {
                if let tomorrow = calendar.date(byAdding: .day, value: 1, to: scheduled) {
                    nextDates.append(tomorrow)
                }
            } else {
                nextDates.append(scheduled)
            }
        }

        return nextDates.min() ?? now.addingTimeInterval(3600)
    }

    private func sendNotification(articleCount: Int) async {
        let center = UNUserNotificationCenter.current()
        do {
            let granted = try await center.requestAuthorization(options: [.alert, .sound])
            guard granted else { return }

            let content = UNMutableNotificationContent()
            content.title = "Digest Ready"
            content.body = "Your Epilogue digest with \(articleCount) articles is ready to read."
            content.sound = .default

            let request = UNNotificationRequest(
                identifier: UUID().uuidString,
                content: content,
                trigger: UNTimeIntervalNotificationTrigger(timeInterval: 1, repeats: false)
            )
            try await center.add(request)
        } catch {
            logger.error("Failed to send notification: \(error.localizedDescription)")
        }
    }
}
