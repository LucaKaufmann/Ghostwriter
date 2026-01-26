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
    @State private var backgroundTaskManager: GhostwriterBackgroundTaskManager?

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

        // Register background tasks
        let taskManager = GhostwriterBackgroundTaskManager(coordinator: coordinator)
        taskManager.registerBackgroundTasks()
        _backgroundTaskManager = State(initialValue: taskManager)
    }

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(ghostwriterCoordinator)
                .environment(\.settingsRepository, settingsRepository)
                .environment(\.feedRepository, feedRepository)
                .environment(\.digestRepository, digestRepository)
                .task {
                    // Perform initial sync on app launch
                    await ghostwriterCoordinator.performFullSync()
                }
                .onReceive(NotificationCenter.default.publisher(for: UIApplication.willResignActiveNotification)) { _ in
                    // Schedule background tasks when app goes to background
                    backgroundTaskManager?.scheduleBackgroundTasks()
                }
        }
        .modelContainer(persistenceController.container)
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
