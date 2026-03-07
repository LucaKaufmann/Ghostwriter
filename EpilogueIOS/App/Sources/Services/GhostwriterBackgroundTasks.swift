//
//  GhostwriterBackgroundTasks.swift
//  Epilogue
//
//  Created on 2026-01-26.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import Foundation
import BackgroundTasks
import OSLog

/// Background task identifiers for Ghostwriter sync
public enum GhostwriterBackgroundTask {
    public static let feedSync = "com.codable.epilogue.feedSync"
    public static let digestSync = "com.codable.epilogue.digestSync"
}

/// Manages background task registration and scheduling for Ghostwriter sync
public final class GhostwriterBackgroundTaskManager {
    private let coordinator: GhostwriterSyncCoordinator
    private let logger = Logger(subsystem: "com.epilogue", category: "BackgroundTasks")

    public init(coordinator: GhostwriterSyncCoordinator) {
        self.coordinator = coordinator
    }

    /// Register background tasks with the system
    /// Call this from application(_:didFinishLaunchingWithOptions:) or App init
    public func registerBackgroundTasks() {
        BGTaskScheduler.shared.register(
            forTaskWithIdentifier: GhostwriterBackgroundTask.feedSync,
            using: nil
        ) { [weak self] task in
            self?.handleFeedSync(task: task as! BGAppRefreshTask)
        }

        BGTaskScheduler.shared.register(
            forTaskWithIdentifier: GhostwriterBackgroundTask.digestSync,
            using: nil
        ) { [weak self] task in
            self?.handleDigestSync(task: task as! BGAppRefreshTask)
        }

        logger.info("Registered Ghostwriter background tasks")
    }

    /// Schedule background sync tasks
    /// Call this when app enters background or after successful sync
    public func scheduleBackgroundTasks() {
        scheduleFeedSync()
        scheduleDigestSync()
    }

    /// Cancel any pending Ghostwriter sync requests.
    public func cancelBackgroundTasks() {
        BGTaskScheduler.shared.cancel(taskRequestWithIdentifier: GhostwriterBackgroundTask.feedSync)
        BGTaskScheduler.shared.cancel(taskRequestWithIdentifier: GhostwriterBackgroundTask.digestSync)
    }

    /// Schedule feed sync task
    public func scheduleFeedSync() {
        BGTaskScheduler.shared.cancel(taskRequestWithIdentifier: GhostwriterBackgroundTask.feedSync)

        let request = BGAppRefreshTaskRequest(identifier: GhostwriterBackgroundTask.feedSync)
        request.earliestBeginDate = Date(timeIntervalSinceNow: 15 * 60) // 15 minutes

        do {
            try BGTaskScheduler.shared.submit(request)
            logger.debug("Scheduled feed sync background task")
        } catch {
            logger.error("Failed to schedule feed sync: \(error.localizedDescription)")
        }
    }

    /// Schedule digest sync task
    public func scheduleDigestSync() {
        BGTaskScheduler.shared.cancel(taskRequestWithIdentifier: GhostwriterBackgroundTask.digestSync)

        let request = BGAppRefreshTaskRequest(identifier: GhostwriterBackgroundTask.digestSync)
        request.earliestBeginDate = Date(timeIntervalSinceNow: 30 * 60) // 30 minutes

        do {
            try BGTaskScheduler.shared.submit(request)
            logger.debug("Scheduled digest sync background task")
        } catch {
            logger.error("Failed to schedule digest sync: \(error.localizedDescription)")
        }
    }

    // MARK: - Task Handlers

    private func handleFeedSync(task: BGAppRefreshTask) {
        logger.info("Handling feed sync background task")

        // Schedule next sync
        scheduleFeedSync()

        let syncTask = Task {
            do {
                try await coordinator.syncFeeds()
                task.setTaskCompleted(success: true)
                logger.info("Feed sync background task completed successfully")
            } catch {
                logger.error("Feed sync background task failed: \(error.localizedDescription)")
                task.setTaskCompleted(success: false)
            }
        }

        // Handle task expiration
        task.expirationHandler = {
            syncTask.cancel()
            self.logger.warning("Feed sync background task expired")
        }
    }

    private func handleDigestSync(task: BGAppRefreshTask) {
        logger.info("Handling digest sync background task")

        // Schedule next sync
        scheduleDigestSync()

        let syncTask = Task {
            do {
                try await coordinator.syncDigests()
                task.setTaskCompleted(success: true)
                logger.info("Digest sync background task completed successfully")
            } catch {
                logger.error("Digest sync background task failed: \(error.localizedDescription)")
                task.setTaskCompleted(success: false)
            }
        }

        // Handle task expiration
        task.expirationHandler = {
            syncTask.cancel()
            self.logger.warning("Digest sync background task expired")
        }
    }
}
