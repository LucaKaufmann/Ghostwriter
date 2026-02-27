//
//  EpilogueApp.swift
//  Epilogue
//
//  Created on 2026-01-26.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import SwiftUI
import SwiftData
import Domain
import Data
import GhostwriterClient

@main
struct EpilogueApp: App {
    let persistenceController = PersistenceController.shared

    // Repositories
    @State private var settingsRepository: SettingsRepository
    @State private var feedRepository: FeedRepository
    @State private var digestRepository: DigestRepository

    // Ghostwriter sync
    @StateObject private var ghostwriterCoordinator: GhostwriterSyncCoordinator
    @StateObject private var localDigestService: LocalDigestService
    @State private var localDigestScheduler: LocalDigestScheduler?
    @State private var backgroundTaskManager: GhostwriterBackgroundTaskManager?

    @Environment(\.scenePhase) private var scenePhase

    init() {
        let persistence = PersistenceController.shared
        let context = persistence.container.mainContext

        // Initialize repositories
        let settings = SettingsRepository()
        let feeds = FeedRepository(modelContext: context)
        let digests = DigestRepository(modelContext: context)

        _settingsRepository = State(initialValue: settings)
        _feedRepository = State(initialValue: feeds)
        _digestRepository = State(initialValue: digests)

        // Initialize Ghostwriter coordinator
        let coordinator = GhostwriterSyncCoordinator(
            settingsRepository: settings,
            feedRepository: feeds,
            digestRepository: digests
        )
        _ghostwriterCoordinator = StateObject(wrappedValue: coordinator)

        // Initialize local digest service
        let localDigest = LocalDigestService(
            feedRepository: feeds,
            digestRepository: digests,
            settingsRepository: settings
        )
        _localDigestService = StateObject(wrappedValue: localDigest)

        // Register background tasks (must happen before scene setup)
        let taskManager = GhostwriterBackgroundTaskManager(coordinator: coordinator)
        taskManager.registerBackgroundTasks()
        _backgroundTaskManager = State(initialValue: taskManager)

        let scheduler = LocalDigestScheduler(
            feedRepository: feeds,
            digestRepository: digests,
            settingsRepository: settings
        )
        scheduler.registerBackgroundTasks()
        _localDigestScheduler = State(initialValue: scheduler)

        // Register notification categories
        LocalDigestScheduler.registerNotificationCategories()
    }

    var body: some Scene {
        WindowGroup {
            ContentView()
                .tint(.primary)
                .environmentObject(ghostwriterCoordinator)
                .environmentObject(localDigestService)
                .environment(\.settingsRepository, settingsRepository)
                .environment(\.feedRepository, feedRepository)
                .environment(\.digestRepository, digestRepository)
                .task {
                    // Perform initial sync on app launch
                    await ghostwriterCoordinator.performFullSync()

                    // PRIMARY: Catch-up — generate missed digest if needed
                    await localDigestScheduler?.checkForMissedDigests()

                    // Set up standing daily reminder notification
                    await localDigestScheduler?.scheduleDigestReminderNotification()

                    // Clean up delivered notifications
                    LocalDigestScheduler.cleanUpDeliveredNotifications()
                }
                .onChange(of: scenePhase) { _, newPhase in
                    if newPhase == .background {
                        scheduleAllBackgroundWork()
                    }
                }
                .onReceive(NotificationCenter.default.publisher(for: UIApplication.willResignActiveNotification)) { _ in
                    scheduleAllBackgroundWork()
                }
        }
        .modelContainer(persistenceController.container)
    }

    private func scheduleAllBackgroundWork() {
        backgroundTaskManager?.scheduleBackgroundTasks()
        localDigestScheduler?.scheduleFeedRefresh()
        Task {
            await localDigestScheduler?.scheduleOvernightDigest()
        }
    }
}

// MARK: - Environment Keys

private struct SettingsRepositoryKey: EnvironmentKey {
    static let defaultValue: SettingsRepositoryProtocol = SettingsRepository()
}

private struct FeedRepositoryKey: EnvironmentKey {
    static let defaultValue: FeedRepositoryProtocol? = nil
}

private struct DigestRepositoryKey: EnvironmentKey {
    static let defaultValue: DigestRepositoryProtocol? = nil
}

extension EnvironmentValues {
    var settingsRepository: SettingsRepositoryProtocol {
        get { self[SettingsRepositoryKey.self] }
        set { self[SettingsRepositoryKey.self] = newValue }
    }

    var feedRepository: FeedRepositoryProtocol? {
        get { self[FeedRepositoryKey.self] }
        set { self[FeedRepositoryKey.self] = newValue }
    }

    var digestRepository: DigestRepositoryProtocol? {
        get { self[DigestRepositoryKey.self] }
        set { self[DigestRepositoryKey.self] = newValue }
    }
}
