//
//  GhostwriterSettingsView.swift
//  Epilogue
//
//  Created on 2026-01-26.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import SwiftUI
import Domain
import GhostwriterClient
import UIKit
import UserNotifications

/// Settings view for configuring Ghostwriter sync
struct GhostwriterSettingsView: View {
    @EnvironmentObject private var coordinator: GhostwriterSyncCoordinator
    @StateObject private var viewModel: GhostwriterSettingsViewModel
    @State private var showingAPIKeyAlert = false

    init(settingsRepository: SettingsRepositoryProtocol) {
        _viewModel = StateObject(wrappedValue: GhostwriterSettingsViewModel(settingsRepository: settingsRepository))
    }

    var body: some View {
        Form {
            // MARK: - Enable/Disable Section
            Section {
                Toggle("Enable Ghostwriter Sync", isOn: $viewModel.isEnabled)
                    .onChange(of: viewModel.isEnabled) { _, newValue in
                        Task { await viewModel.setEnabled(newValue) }
                    }
            } footer: {
                Text("When enabled, feeds and digests will sync with your Ghostwriter server.")
            }

            // MARK: - Server Configuration
            Section("Server") {
                TextField("Server URL", text: $viewModel.serverURL)
                    .keyboardType(.URL)
                    .textContentType(.URL)
                    .autocapitalization(.none)
                    .autocorrectionDisabled()
                    .disabled(!viewModel.isEnabled)
                    .onSubmit {
                        Task { await viewModel.saveServerURL() }
                    }
                    .onChange(of: viewModel.serverURL) {
                        viewModel.scheduleSaveURL()
                    }

                HStack {
                    if viewModel.hasAPIKey {
                        Text("API Token")
                        Spacer()
                        Text("••••••••")
                            .foregroundColor(.secondary)
                        Button("Change") {
                            showingAPIKeyAlert = true
                        }
                        .buttonStyle(.borderless)
                    } else {
                        Button("Set API Token") {
                            showingAPIKeyAlert = true
                        }
                    }
                }
                .disabled(!viewModel.isEnabled)
                Text("Use a Ghostwriter API token (gw_...) or a JWT from the web UI.")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }

            // MARK: - Push Notifications
            Section {
                Toggle("Notify When Digest Is Ready", isOn: $viewModel.pushEnabled)
                    .disabled(!viewModel.isConfigured)
                    .onChange(of: viewModel.pushEnabled) { _, newValue in
                        Task { await viewModel.setPushEnabled(newValue) }
                    }

                if let error = viewModel.pushError {
                    Text(error)
                        .font(.caption)
                        .foregroundColor(.red)
                }
            } header: {
                Text("Notifications")
            } footer: {
                Text("When enabled, Ghostwriter will send a notification when a new digest is available. iOS may also fetch it in the background.")
            }

            // MARK: - Connection Test
            Section {
                Button {
                    Task { await viewModel.testConnection() }
                } label: {
                    HStack {
                        Text("Test Connection")
                        Spacer()
                        if viewModel.isTesting {
                            ProgressView()
                        } else if let status = viewModel.connectionStatus {
                            connectionStatusIcon(status)
                        }
                    }
                }
                .disabled(!viewModel.isEnabled || viewModel.serverURL.isEmpty)

                if let health = viewModel.serverHealth {
                    VStack(alignment: .leading, spacing: 4) {
                        LabeledContent("Version", value: health.version)
                        LabeledContent("AI Provider", value: health.aiProvider)
                        LabeledContent("AI Model", value: health.aiModel)
                        if let uptime = health.formattedUptime {
                            LabeledContent("Uptime", value: uptime)
                        }
                    }
                    .font(.caption)
                    .foregroundColor(.secondary)
                }

                if let error = viewModel.connectionError {
                    Text(error)
                        .font(.caption)
                        .foregroundColor(.red)
                }
            }

            // MARK: - Sync Actions
            Section("Sync") {
                Button {
                    Task { await coordinator.performFullSync() }
                } label: {
                    HStack {
                        Label("Sync Now", systemImage: "arrow.triangle.2.circlepath")
                        Spacer()
                        if coordinator.isSyncing {
                            ProgressView()
                        }
                    }
                }
                .disabled(!viewModel.isConfigured || coordinator.isSyncing)

                Button {
                    Task { await viewModel.triggerDigest() }
                } label: {
                    HStack {
                        Label("Generate Digest on Server", systemImage: "doc.badge.plus")
                        Spacer()
                        if viewModel.isTriggering {
                            ProgressView()
                        }
                    }
                }
                .disabled(!viewModel.isConfigured || viewModel.isTriggering)

                if let lastSync = coordinator.lastSyncTime ?? viewModel.lastSyncTime {
                    LabeledContent("Last Sync", value: lastSync.formatted(date: .abbreviated, time: .shortened))
                        .font(.caption)
                        .foregroundColor(.secondary)
                }

                if let error = coordinator.lastSyncError {
                    Text("Sync error: \(error.localizedDescription)")
                        .font(.caption)
                        .foregroundColor(.red)
                }
            }

            // MARK: - Server Schedule
            if viewModel.isConfigured, let schedule = viewModel.serverSchedule {
                Section("Server Schedule") {
                    LabeledContent("Morning", value: schedule.formattedMorning())
                    LabeledContent("Noon", value: schedule.formattedNoon())
                    LabeledContent("Evening", value: schedule.formattedEvening())
                    LabeledContent("Timezone", value: schedule.timezone)
                }
            }

            // MARK: - Status
            if viewModel.isConfigured {
                Section("Status") {
                    if let status = viewModel.clientStatus {
                        if status.areSchedulesActive {
                            Label("Server schedules active", systemImage: "checkmark.circle.fill")
                                .foregroundColor(.green)
                        } else {
                            Label("Server schedules disabled", systemImage: "exclamationmark.triangle.fill")
                                .foregroundColor(.orange)
                        }

                        if let daysUntil = status.daysUntilAutoDisable {
                            Text("Schedules will auto-disable in \(daysUntil) days without activity")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    }
                }
            }

            // MARK: - Integrations
            if viewModel.wallabagIntegration != nil || viewModel.newslettersIntegration != nil {
                Section("Integrations") {
                    if let wallabag = viewModel.wallabagIntegration {
                        HStack {
                            Label("Wallabag", systemImage: "bookmark.fill")
                            Spacer()
                            if wallabag.enabled {
                                Text("Enabled")
                                    .foregroundColor(.green)
                            } else {
                                Text("Not configured")
                                    .foregroundColor(.secondary)
                            }
                        }
                    }

                    if let newsletters = viewModel.newslettersIntegration {
                        VStack(alignment: .leading, spacing: 4) {
                            HStack {
                                Label("Newsletters", systemImage: "envelope.fill")
                                Spacer()
                                if newsletters.enabled {
                                    Text("Enabled")
                                        .foregroundColor(.green)
                                } else {
                                    Text("Not configured")
                                        .foregroundColor(.secondary)
                                }
                            }
                            if newsletters.enabled, let label = newsletters.label {
                                Text("Gmail label: \(label)")
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                            }
                        }
                    }
                }
            }
        }
        .navigationTitle("Ghostwriter")
        .alert("API Token", isPresented: $showingAPIKeyAlert) {
            TextField("API Token (gw_... or JWT)", text: $viewModel.newAPIKey)
            Button("Cancel", role: .cancel) {
                viewModel.newAPIKey = ""
            }
            Button("Save") {
                Task { await viewModel.saveAPIKey() }
            }
        } message: {
            Text("Enter your Ghostwriter API token")
        }
        .task {
            await viewModel.load()
        }
        .onDisappear {
            Task { await viewModel.saveServerURL() }
        }
    }

    @ViewBuilder
    private func connectionStatusIcon(_ status: ConnectionStatus) -> some View {
        switch status {
        case .connected:
            Image(systemName: "checkmark.circle.fill")
                .foregroundColor(.green)
        case .failed:
            Image(systemName: "xmark.circle.fill")
                .foregroundColor(.red)
        case .unknown:
            Image(systemName: "questionmark.circle")
                .foregroundColor(.secondary)
        }
    }
}

// MARK: - View Model

enum ConnectionStatus {
    case connected
    case failed
    case unknown
}

@MainActor
class GhostwriterSettingsViewModel: ObservableObject {
    private let settingsRepository: SettingsRepositoryProtocol

    @Published var isEnabled = false
    @Published var serverURL = ""
    @Published var hasAPIKey = false
    @Published var newAPIKey = ""
    @Published var pushEnabled = false
    @Published var pushError: String?
    @Published var connectionStatus: ConnectionStatus?
    @Published var connectionError: String?
    @Published var serverHealth: HealthResponse?
    @Published var clientStatus: ClientStatusResponse?
    @Published var serverSchedule: GhostwriterSchedule?
    @Published var wallabagIntegration: IntegrationStatus?
    @Published var newslettersIntegration: IntegrationStatus?
    @Published var lastSyncTime: Date?
    @Published var isTesting = false
    @Published var isSyncing = false
    @Published var isTriggering = false

    private var saveURLTask: Task<Void, Never>?

    var isConfigured: Bool {
        isEnabled && !serverURL.isEmpty
    }

    init(settingsRepository: SettingsRepositoryProtocol) {
        self.settingsRepository = settingsRepository
    }

    func load() async {
        do {
            isEnabled = try await settingsRepository.isGhostwriterEnabled()
            serverURL = try await settingsRepository.getGhostwriterURL() ?? ""
            hasAPIKey = (try await settingsRepository.getGhostwriterAPIKey()) != nil
            pushEnabled = try await settingsRepository.isGhostwriterPushEnabled()
            lastSyncTime = try await settingsRepository.getLastFeedSyncTime()
            serverSchedule = try await settingsRepository.getGhostwriterSchedule()

            if isConfigured {
                await refreshClientStatus()
            }
        } catch {
            // Ignore load errors
        }
    }

    func setEnabled(_ enabled: Bool) async {
        do {
            try await settingsRepository.setGhostwriterEnabled(enabled)
            if !enabled {
                pushEnabled = false
                try? await settingsRepository.setGhostwriterPushEnabled(false)
                await GhostwriterPushService.unregisterCurrentDevice()
                UIApplication.shared.unregisterForRemoteNotifications()
            }
        } catch {
            isEnabled = !enabled // Revert on error
        }
    }

    func scheduleSaveURL() {
        saveURLTask?.cancel()
        saveURLTask = Task {
            try? await Task.sleep(nanoseconds: 500_000_000)
            guard !Task.isCancelled else { return }
            await saveServerURL()
        }
    }

    func saveServerURL() async {
        saveURLTask?.cancel()
        do {
            try await settingsRepository.setGhostwriterURL(serverURL.isEmpty ? nil : serverURL)
        } catch {
            // Ignore save errors
        }
    }

    func saveAPIKey() async {
        do {
            try await settingsRepository.setGhostwriterAPIKey(newAPIKey.isEmpty ? nil : newAPIKey)
            hasAPIKey = !newAPIKey.isEmpty
            newAPIKey = ""
        } catch {
            // Ignore save errors
        }
    }

    func setPushEnabled(_ enabled: Bool) async {
        pushError = nil

        guard isConfigured else {
            pushEnabled = false
            try? await settingsRepository.setGhostwriterPushEnabled(false)
            return
        }

        if enabled {
            let granted = await requestNotificationPermission()
            guard granted else {
                pushEnabled = false
                try? await settingsRepository.setGhostwriterPushEnabled(false)
                pushError = "Notifications permission is not granted."
                return
            }

            do {
                try await settingsRepository.setGhostwriterPushEnabled(true)
                UIApplication.shared.registerForRemoteNotifications()
            } catch {
                pushEnabled = false
                pushError = error.localizedDescription
            }
        } else {
            do {
                try await settingsRepository.setGhostwriterPushEnabled(false)
            } catch {
                pushError = error.localizedDescription
            }
            UIApplication.shared.unregisterForRemoteNotifications()
            await GhostwriterPushService.unregisterCurrentDevice()
        }
    }

    private func requestNotificationPermission() async -> Bool {
        do {
            return try await withCheckedThrowingContinuation { continuation in
                UNUserNotificationCenter.current().requestAuthorization(
                    options: [.alert, .badge, .sound]
                ) { granted, error in
                    if let error {
                        continuation.resume(throwing: error)
                    } else {
                        continuation.resume(returning: granted)
                    }
                }
            }
        } catch {
            pushError = error.localizedDescription
            return false
        }
    }

    func testConnection() async {
        guard !serverURL.isEmpty else { return }

        await saveServerURL()

        isTesting = true
        connectionError = nil
        connectionStatus = nil
        serverHealth = nil

        do {
            let apiKey = try await settingsRepository.getGhostwriterAPIKey()
            let client = try GhostwriterClient(baseURLString: serverURL, apiKey: apiKey)

            let health = try await client.checkHealth()
            serverHealth = health
            connectionStatus = health.isHealthy ? .connected : .failed

            if health.isHealthy, let token = apiKey, !token.isEmpty {
                do {
                    _ = try await client.getConfig()
                } catch {
                    connectionStatus = .failed
                    connectionError = error.localizedDescription
                }
            }

            // Also get client status and integrations
            await refreshClientStatus()
            await fetchIntegrationStatus()
        } catch {
            connectionStatus = .failed
            connectionError = error.localizedDescription
        }

        isTesting = false
    }

    func syncNow() async {
        // This would need access to the coordinator
        // For now, just update the last sync time
        isSyncing = true
        try? await Task.sleep(nanoseconds: 1_000_000_000) // Simulate sync
        lastSyncTime = Date()
        isSyncing = false
    }

    func triggerDigest() async {
        guard !serverURL.isEmpty else { return }

        isTriggering = true

        do {
            let apiKey = try await settingsRepository.getGhostwriterAPIKey()
            let client = try GhostwriterClient(baseURLString: serverURL, apiKey: apiKey)
            _ = try await client.triggerDigest(period: "manual")
        } catch {
            // Show error
        }

        isTriggering = false
    }

    private func refreshClientStatus() async {
        do {
            let apiKey = try await settingsRepository.getGhostwriterAPIKey()
            let client = try GhostwriterClient(baseURLString: serverURL, apiKey: apiKey)
            clientStatus = try await client.getClientStatus()
        } catch {
            // Ignore status errors
        }
    }

    private func fetchIntegrationStatus() async {
        do {
            let apiKey = try await settingsRepository.getGhostwriterAPIKey()
            let client = try GhostwriterClient(baseURLString: serverURL, apiKey: apiKey)
            let config = try await client.getConfig()
            wallabagIntegration = config.wallabag
            newslettersIntegration = config.newsletters
        } catch {
            // Ignore integration status errors
        }
    }
}

// MARK: - Preview

#Preview {
    NavigationStack {
        GhostwriterSettingsView(settingsRepository: MockSettingsRepository())
    }
}

// Mock for previews
private final class MockSettingsRepository: SettingsRepositoryProtocol, @unchecked Sendable {
    func getOpenAIKey() async throws -> String? { nil }
    func setOpenAIKey(_ key: String) async throws {}
    func deleteOpenAIKey() async throws {}

    // Schedule
    func getEnabledPeriods() async throws -> Set<DigestPeriod> { [.morning] }
    func setEnabledPeriods(_ periods: Set<DigestPeriod>) async throws {}
    func togglePeriod(_ period: DigestPeriod, enabled: Bool) async throws {}
    func isPeriodEnabled(_ period: DigestPeriod) async throws -> Bool { period == .morning }
    func isScheduleEnabled() async throws -> Bool { true }
    func getScheduledHour() async throws -> Int { 6 }
    func setScheduledHour(_ hour: Int) async throws {}
    func setScheduleEnabled(_ enabled: Bool) async throws {}

    func getMinWordCount() async throws -> Int { 300 }
    func setMinWordCount(_ count: Int) async throws {}
    func getAIProvider() async throws -> AIProvider { .openAI }
    func setAIProvider(_ provider: AIProvider) async throws {}
    func getAIModel() async throws -> String { "gpt-4o-mini" }
    func setAIModel(_ model: String) async throws {}
    func shouldShowNotifications() async throws -> Bool { true }
    func setShouldShowNotifications(_ enabled: Bool) async throws {}

    // Display
    func isEinkModeEnabled() async throws -> Bool { false }
    func setEinkModeEnabled(_ enabled: Bool) async throws {}
    func getCustomExportEnabled() async throws -> Bool { false }
    func setCustomExportEnabled(_ enabled: Bool) async throws {}
    func getCustomExportBookmark() async throws -> Data? { nil }
    func setCustomExportBookmark(_ bookmark: Data?) async throws {}

    // Ghostwriter
    func isGhostwriterEnabled() async throws -> Bool { true }
    func setGhostwriterEnabled(_ enabled: Bool) async throws {}
    func getGhostwriterURL() async throws -> String? { "https://ghostwriter.example.com" }
    func setGhostwriterURL(_ url: String?) async throws {}
    func getGhostwriterAPIKey() async throws -> String? { "test-key" }
    func setGhostwriterAPIKey(_ key: String?) async throws {}
    func getLastFeedSyncTime() async throws -> Date? { Date() }
    func setLastFeedSyncTime(_ date: Date?) async throws {}
    func getLastDigestSyncTime() async throws -> Date? { nil }
    func setLastDigestSyncTime(_ date: Date?) async throws {}
    func getGhostwriterConfigUpdatedAt() async throws -> String? { nil }
    func setGhostwriterConfigUpdatedAt(_ timestamp: String?) async throws {}
    func isGhostwriterConfigured() async throws -> Bool { true }
    func setGhostwriterSchedule(morningHour: Int, morningMinute: Int, noonHour: Int, noonMinute: Int, eveningHour: Int, eveningMinute: Int, timezone: String) async throws {}
    func getGhostwriterSchedule() async throws -> GhostwriterSchedule? {
        GhostwriterSchedule(morningHour: 7, morningMinute: 0, noonHour: 12, noonMinute: 0, eveningHour: 18, eveningMinute: 0, timezone: "Europe/Helsinki")
    }

    // Ghostwriter push notifications
    func isGhostwriterPushEnabled() async throws -> Bool { false }
    func setGhostwriterPushEnabled(_ enabled: Bool) async throws {}
    func getGhostwriterDeviceId() async throws -> String { "mock-device-id" }
}
