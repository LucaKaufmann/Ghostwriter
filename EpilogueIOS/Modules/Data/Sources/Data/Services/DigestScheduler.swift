//
//  DigestScheduler.swift
//  Epilogue
//
//  Created on 2026-01-26.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import Foundation
import BackgroundTasks
import UserNotifications
import Domain

/// Service for scheduling and managing background digest generation
///
/// When Ghostwriter is enabled, local digest generation is disabled.
/// The Ghostwriter server handles scheduling according to the same periods.
@MainActor
public final class DigestScheduler {
    public static let taskIdentifier = "com.epilogue.app.digestgeneration"

    private let digestGenerator: DigestGenerator
    private let settingsRepository: SettingsRepositoryProtocol
    private let notificationCenter = UNUserNotificationCenter.current()

    public init(
        digestGenerator: DigestGenerator,
        settingsRepository: SettingsRepositoryProtocol
    ) {
        self.digestGenerator = digestGenerator
        self.settingsRepository = settingsRepository
    }

    /// Register the background task handler
    public func registerBackgroundTasks() {
        BGTaskScheduler.shared.register(
            forTaskWithIdentifier: Self.taskIdentifier,
            using: nil
        ) { task in
            Task {
                await self.handleBackgroundTask(task as! BGProcessingTask)
            }
        }
    }

    /// Schedule the next background digest generation
    /// Schedules tasks for all enabled periods (morning, noon, evening)
    public func scheduleNextDigest() async throws {
        // Cancel existing tasks
        BGTaskScheduler.shared.cancel(taskRequestWithIdentifier: Self.taskIdentifier)

        // Skip local scheduling if Ghostwriter is enabled
        let ghostwriterEnabled = try await settingsRepository.isGhostwriterEnabled()
        if ghostwriterEnabled {
            return // Server handles scheduling
        }

        // Get enabled periods
        let enabledPeriods = try await settingsRepository.getEnabledPeriods()
        guard !enabledPeriods.isEmpty else {
            return
        }

        // Find the next scheduled time from enabled periods
        let nextRunDate = calculateNextRunDate(for: enabledPeriods)

        // Create background task request
        let request = BGProcessingTaskRequest(identifier: Self.taskIdentifier)
        request.earliestBeginDate = nextRunDate
        request.requiresNetworkConnectivity = true
        request.requiresExternalPower = false

        do {
            try BGTaskScheduler.shared.submit(request)
        } catch {
            throw DigestSchedulerError.schedulingFailed(error.localizedDescription)
        }
    }

    /// Generate digest manually (Run Now functionality)
    /// Returns nil if Ghostwriter is enabled (use GhostwriterSyncCoordinator instead)
    public func generateDigestNow() async throws -> Digest? {
        // Check if Ghostwriter is enabled
        let ghostwriterEnabled = try await settingsRepository.isGhostwriterEnabled()
        if ghostwriterEnabled {
            // Don't generate locally - caller should use GhostwriterSyncCoordinator
            return nil
        }

        let digest = try await digestGenerator.generateDigest(triggerType: .manual)

        // Send notification if enabled
        let shouldNotify = try await settingsRepository.shouldShowNotifications()
        if shouldNotify {
            try await sendCompletionNotification(digest: digest)
        }

        // Schedule next automatic digest
        try await scheduleNextDigest()

        return digest
    }

    /// Check if local generation is available (not using Ghostwriter)
    public func isLocalGenerationEnabled() async throws -> Bool {
        let ghostwriterEnabled = try await settingsRepository.isGhostwriterEnabled()
        return !ghostwriterEnabled
    }

    // MARK: - Private Helpers

    private func handleBackgroundTask(_ task: BGProcessingTask) async {
        // Set expiration handler
        task.expirationHandler = {
            task.setTaskCompleted(success: false)
        }

        // Skip if Ghostwriter is enabled
        do {
            let ghostwriterEnabled = try await settingsRepository.isGhostwriterEnabled()
            if ghostwriterEnabled {
                task.setTaskCompleted(success: true)
                return
            }
        } catch {
            task.setTaskCompleted(success: false)
            return
        }

        do {
            // Generate digest
            let digest = try await digestGenerator.generateDigest(triggerType: .scheduled)

            // Send notification if enabled
            let shouldNotify = try await settingsRepository.shouldShowNotifications()
            if shouldNotify {
                try await sendCompletionNotification(digest: digest)
            }

            // Schedule next run
            try await scheduleNextDigest()

            task.setTaskCompleted(success: true)

        } catch {
            print("Background digest generation failed: \(error)")
            task.setTaskCompleted(success: false)

            // Retry by scheduling next attempt
            try? await scheduleNextDigest()
        }
    }

    private func calculateNextRunDate(for periods: Set<DigestPeriod>) -> Date {
        let calendar = Calendar.current
        let now = Date()

        // Get all possible next run times for each enabled period
        var nextDates: [Date] = []

        for period in periods {
            // Get today at the period's hour
            var components = calendar.dateComponents([.year, .month, .day], from: now)
            components.hour = period.hour
            components.minute = period.minute
            components.second = 0

            guard let scheduledToday = calendar.date(from: components) else {
                continue
            }

            // If scheduled time has passed today, use tomorrow
            if scheduledToday <= now {
                if let tomorrow = calendar.date(byAdding: .day, value: 1, to: scheduledToday) {
                    nextDates.append(tomorrow)
                }
            } else {
                nextDates.append(scheduledToday)
            }
        }

        // Return the earliest next date
        return nextDates.min() ?? now.addingTimeInterval(3600)
    }

    private func sendCompletionNotification(digest: Digest) async throws {
        // Request notification permission
        let granted = try await notificationCenter.requestAuthorization(options: [.alert, .sound])
        guard granted else { return }

        // Create notification content
        let content = UNMutableNotificationContent()
        content.title = "Digest Ready"
        content.body = "Your Epilogue digest with \(digest.articleCount) articles is ready to read."
        content.sound = .default

        // Create trigger (deliver immediately)
        let trigger = UNTimeIntervalNotificationTrigger(timeInterval: 1, repeats: false)

        // Create request
        let request = UNNotificationRequest(
            identifier: digest.id.uuidString,
            content: content,
            trigger: trigger
        )

        // Add notification
        try await notificationCenter.add(request)
    }

    /// Request notification permissions
    public func requestNotificationPermissions() async throws -> Bool {
        try await notificationCenter.requestAuthorization(options: [.alert, .sound, .badge])
    }
}

// MARK: - Errors

public enum DigestSchedulerError: LocalizedError {
    case schedulingFailed(String)
    case notificationPermissionDenied

    public var errorDescription: String? {
        switch self {
        case .schedulingFailed(let message):
            return "Failed to schedule background task: \(message)"
        case .notificationPermissionDenied:
            return "Notification permission was denied"
        }
    }
}
