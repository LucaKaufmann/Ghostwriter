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
    public func scheduleNextDigest() async throws {
        // Cancel existing tasks
        BGTaskScheduler.shared.cancel(taskRequestWithIdentifier: Self.taskIdentifier)

        // Check if scheduling is enabled
        let isEnabled = try await settingsRepository.isScheduleEnabled()
        guard isEnabled else {
            return
        }

        // Get scheduled hour
        let scheduledHour = try await settingsRepository.getScheduledHour()

        // Calculate next run time
        let nextRunDate = calculateNextRunDate(hour: scheduledHour)

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
    public func generateDigestNow() async throws -> Digest {
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

    // MARK: - Private Helpers

    private func handleBackgroundTask(_ task: BGProcessingTask) async {
        // Set expiration handler
        task.expirationHandler = {
            task.setTaskCompleted(success: false)
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

    private func calculateNextRunDate(hour: Int) -> Date {
        let calendar = Calendar.current
        let now = Date()

        // Get today at the scheduled hour
        var components = calendar.dateComponents([.year, .month, .day], from: now)
        components.hour = hour
        components.minute = 0
        components.second = 0

        guard let scheduledToday = calendar.date(from: components) else {
            return now.addingTimeInterval(3600) // Fallback to 1 hour from now
        }

        // If scheduled time has passed today, schedule for tomorrow
        if scheduledToday <= now {
            return calendar.date(byAdding: .day, value: 1, to: scheduledToday) ?? scheduledToday
        }

        return scheduledToday
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
