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

/// Settings view for configuring Ghostwriter sync
struct GhostwriterSettingsView: View {
    @EnvironmentObject private var coordinator: GhostwriterSyncCoordinator
    @Environment(\.openURL) private var openURL
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

                Toggle("Download EPUBs on Sync", isOn: $viewModel.downloadEpubsOnSync)
                    .disabled(!viewModel.isConfigured)
                    .onChange(of: viewModel.downloadEpubsOnSync) { _, newValue in
                        Task { await viewModel.setDownloadEpubsOnSync(newValue) }
                    }

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
                Text("When off, digest metadata syncs first and EPUB files can be downloaded manually from History.")
                    .font(.caption)
                    .foregroundColor(.secondary)
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
                        HStack(spacing: 12) {
                            Button("Preview") {
                                Task { await viewModel.previewWallabag() }
                            }
                            .disabled(viewModel.integrationActionRunning)

                            Button("Clear Seen") {
                                Task { await viewModel.clearWallabagSeen() }
                            }
                            .disabled(viewModel.integrationActionRunning)
                        }
                        .buttonStyle(.bordered)
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
                            HStack(spacing: 12) {
                                Button("Connect") {
                                    if let url = viewModel.newsletterOAuthStartURL() {
                                        openURL(url)
                                    } else {
                                        viewModel.integrationActionMessage = "Set a valid server URL first."
                                    }
                                }
                                .disabled(viewModel.integrationActionRunning)

                                Button("Preview") {
                                    Task { await viewModel.previewNewsletters() }
                                }
                                .disabled(viewModel.integrationActionRunning)
                            }
                            .buttonStyle(.bordered)

                            Button("Clear Seen") {
                                Task { await viewModel.clearNewslettersSeen() }
                            }
                            .buttonStyle(.bordered)
                            .disabled(viewModel.integrationActionRunning)
                        }
                    }
                }
            }

            // MARK: - Media
            if viewModel.isConfigured {
                Section("Media") {
                    LabeledContent("Podcast Feeds", value: "\(viewModel.podcastFeedCount)")
                    LabeledContent("YouTube Feeds", value: "\(viewModel.youtubeFeedCount)")

                    if let status = viewModel.mediaStatus {
                        Text(
                            "Queue: \(status.pendingCount) pending, \(status.processingCount) processing, " +
                                "\(status.completedCount) completed, \(status.failedCount) failed"
                        )
                        .font(.caption)
                        .foregroundColor(.secondary)

                        if let current = status.currentItemTitle, !current.isEmpty {
                            Text("Current: \(current)")
                                .font(.caption)
                                .foregroundColor(.secondary)
                                .lineLimit(1)
                        }
                    }

                    if !viewModel.recentMediaItems.isEmpty {
                        Text("Recent Items")
                            .font(.caption)
                            .foregroundColor(.secondary)
                        ForEach(viewModel.recentMediaItems, id: \.id) { item in
                            let typeLabel = item.contentType.lowercased() == "podcast"
                                ? "Podcast"
                                : (item.contentType.lowercased() == "youtube" ? "YouTube" : item.contentType)
                            Text("[\(typeLabel) • \(item.status)] \(item.title)")
                                .font(.caption)
                                .lineLimit(1)
                        }
                    }

                    HStack(spacing: 12) {
                        Button("Refresh") {
                            Task { await viewModel.refreshMediaOverview() }
                        }
                        .disabled(viewModel.mediaActionRunning)

                        Button("Trigger") {
                            Task { await viewModel.triggerMediaProcessing() }
                        }
                        .disabled(viewModel.mediaActionRunning)
                    }
                }
            }

            digestContentSection
            coverSettingsSection

            // MARK: - Diagnostics
            if viewModel.isConfigured {
                Section("Diagnostics") {
                    Button {
                        Task { await viewModel.refreshLogFiles() }
                    } label: {
                        HStack {
                            Text("Refresh Logs")
                            Spacer()
                            if viewModel.logsActionRunning {
                                ProgressView()
                            }
                        }
                    }
                    .disabled(viewModel.logsActionRunning)

                    if !viewModel.logFiles.isEmpty {
                        ForEach(viewModel.logFiles, id: \.filename) { log in
                            Text("\(log.filename) (\(log.sizeBytes / 1024) KB)")
                                .font(.caption)
                                .lineLimit(1)
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
        .alert("Integrations", isPresented: Binding(
            get: { viewModel.integrationActionMessage != nil },
            set: { if !$0 { viewModel.integrationActionMessage = nil } }
        )) {
            Button("OK", role: .cancel) {
                viewModel.integrationActionMessage = nil
            }
        } message: {
            Text(viewModel.integrationActionMessage ?? "")
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

    @ViewBuilder
    private var digestContentSection: some View {
        if viewModel.isConfigured {
            Section {
                Toggle(
                    "Include podcasts",
                    isOn: Binding(
                        get: { viewModel.includePodcastsInDigest },
                        set: { newValue in
                            Task { await viewModel.setIncludePodcastsInDigest(newValue) }
                        }
                    )
                )
                .disabled(viewModel.configActionRunning)

                Toggle(
                    "Include YouTube",
                    isOn: Binding(
                        get: { viewModel.includeYoutubeInDigest },
                        set: { newValue in
                            Task { await viewModel.setIncludeYoutubeInDigest(newValue) }
                        }
                    )
                )
                .disabled(viewModel.configActionRunning)
            } header: {
                Text("Digest Content")
            } footer: {
                Text("Controls whether completed media transcripts are included in generated digests.")
            }
        }
    }

    @ViewBuilder
    private var coverSettingsSection: some View {
        if viewModel.isConfigured {
            Section {
                Toggle(
                    "Generate AI covers",
                    isOn: Binding(
                        get: { viewModel.coverEnabled },
                        set: { newValue in
                            Task { await viewModel.setCoverEnabled(newValue) }
                        }
                    )
                )
                .disabled(viewModel.configActionRunning)

                Toggle(
                    "Overlay digest metadata",
                    isOn: Binding(
                        get: { viewModel.coverOverlayEnabled },
                        set: { newValue in
                            Task { await viewModel.setCoverOverlayEnabled(newValue) }
                        }
                    )
                )
                .disabled(!viewModel.coverEnabled || viewModel.configActionRunning)
            } header: {
                Text("Covers")
            } footer: {
                Text("Overlay adds deterministic title/date/source labels on AI-generated covers.")
            }
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
    @Published var downloadEpubsOnSync = true
    @Published var newAPIKey = ""
    @Published var connectionStatus: ConnectionStatus?
    @Published var connectionError: String?
    @Published var serverHealth: HealthResponse?
    @Published var clientStatus: ClientStatusResponse?
    @Published var serverSchedule: GhostwriterSchedule?
    @Published var wallabagIntegration: IntegrationStatus?
    @Published var newslettersIntegration: IntegrationStatus?
    @Published var integrationActionMessage: String?
    @Published var integrationActionRunning = false
    @Published var configActionRunning = false
    @Published var includePodcastsInDigest = true
    @Published var includeYoutubeInDigest = true
    @Published var coverEnabled = false
    @Published var coverOverlayEnabled = true
    @Published var podcastFeedCount = 0
    @Published var youtubeFeedCount = 0
    @Published var mediaStatus: MediaProcessingStatusResponse?
    @Published var recentMediaItems: [MediaItemSummaryResponse] = []
    @Published var mediaActionRunning = false
    @Published var logFiles: [LogFileInfoResponse] = []
    @Published var logsActionRunning = false
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
            downloadEpubsOnSync = try await settingsRepository.getGhostwriterDownloadEpubsOnSync()
            lastSyncTime = try await settingsRepository.getLastFeedSyncTime()
            serverSchedule = try await settingsRepository.getGhostwriterSchedule()

            if isConfigured {
                await refreshClientStatus()
                await fetchIntegrationStatus()
                await refreshMediaOverview()
                await refreshLogFiles()
            }
        } catch {
            // Ignore load errors
        }
    }

    func setEnabled(_ enabled: Bool) async {
        do {
            try await settingsRepository.setGhostwriterEnabled(enabled)
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

    func setDownloadEpubsOnSync(_ enabled: Bool) async {
        do {
            try await settingsRepository.setGhostwriterDownloadEpubsOnSync(enabled)
        } catch {
            downloadEpubsOnSync = !enabled
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
            await refreshMediaOverview()
            await refreshLogFiles()
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
            applyConfig(config)
            try await settingsRepository.setGhostwriterConfigUpdatedAt(config.updatedAt)
        } catch {
            // Ignore integration status errors
        }
    }

    func setIncludePodcastsInDigest(_ enabled: Bool) async {
        await updateConfigToggle(
            applyOptimistic: { includePodcastsInDigest = enabled },
            rollback: { includePodcastsInDigest.toggle() }
        ) { timestamp in
            ClientConfigUpdateRequest(
                includePodcastsInDigest: enabled,
                clientUpdatedAt: timestamp
            )
        }
    }

    func setIncludeYoutubeInDigest(_ enabled: Bool) async {
        await updateConfigToggle(
            applyOptimistic: { includeYoutubeInDigest = enabled },
            rollback: { includeYoutubeInDigest.toggle() }
        ) { timestamp in
            ClientConfigUpdateRequest(
                includeYoutubeInDigest: enabled,
                clientUpdatedAt: timestamp
            )
        }
    }

    func setCoverEnabled(_ enabled: Bool) async {
        await updateConfigToggle(
            applyOptimistic: { coverEnabled = enabled },
            rollback: { coverEnabled.toggle() }
        ) { timestamp in
            ClientConfigUpdateRequest(
                coverEnabled: enabled,
                clientUpdatedAt: timestamp
            )
        }
    }

    func setCoverOverlayEnabled(_ enabled: Bool) async {
        await updateConfigToggle(
            applyOptimistic: { coverOverlayEnabled = enabled },
            rollback: { coverOverlayEnabled.toggle() }
        ) { timestamp in
            ClientConfigUpdateRequest(
                coverOverlayEnabled: enabled,
                clientUpdatedAt: timestamp
            )
        }
    }

    func refreshMediaOverview() async {
        guard !serverURL.isEmpty else { return }
        mediaActionRunning = true
        defer { mediaActionRunning = false }

        do {
            let client = try await createClient()
            async let podcasts = client.getPodcastFeeds()
            async let youtube = client.getYouTubeFeeds()
            async let podcastItems = client.getAllPodcastItems()
            async let youtubeItems = client.getAllYouTubeItems()
            async let status = client.getMediaProcessingStatus()

            let (podcastFeeds, youtubeFeeds, podcastSummaries, youtubeSummaries, processingStatus) =
                try await (podcasts, youtube, podcastItems, youtubeItems, status)
            podcastFeedCount = podcastFeeds.count
            youtubeFeedCount = youtubeFeeds.count
            recentMediaItems = (podcastSummaries + youtubeSummaries)
                .sorted { $0.createdAt > $1.createdAt }
                .prefix(8)
                .map { $0 }
            mediaStatus = processingStatus
        } catch {
            integrationActionMessage = "Failed to load media status: \(error.localizedDescription)"
        }
    }

    func triggerMediaProcessing() async {
        guard !serverURL.isEmpty else { return }
        mediaActionRunning = true
        defer { mediaActionRunning = false }

        do {
            let client = try await createClient()
            let response = try await client.triggerMediaProcessing()
            integrationActionMessage = response.detail ?? "Media processing triggered"
            await refreshMediaOverview()
        } catch {
            integrationActionMessage = "Failed to trigger media processing: \(error.localizedDescription)"
        }
    }

    func refreshLogFiles() async {
        guard !serverURL.isEmpty else { return }
        logsActionRunning = true
        defer { logsActionRunning = false }

        do {
            let client = try await createClient()
            logFiles = try await client.getLogFiles()
                .sorted { $0.modifiedAt > $1.modifiedAt }
                .prefix(8)
                .map { $0 }
        } catch {
            integrationActionMessage = "Failed to load logs: \(error.localizedDescription)"
        }
    }

    func newsletterOAuthStartURL() -> URL? {
        let trimmed = serverURL.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, let base = URL(string: trimmed) else { return nil }
        if base.pathComponents.contains("api") {
            return base.appendingPathComponent("newsletters/oauth/start")
        }
        return base.appendingPathComponent("api/newsletters/oauth/start")
    }

    func previewWallabag() async {
        await runIntegrationAction {
            let client = try await self.createClient()
            let response = try await client.previewWallabag()
            return self.formatPreviewMessage(source: "Wallabag", response: response)
        }
    }

    func previewNewsletters() async {
        await runIntegrationAction {
            let client = try await self.createClient()
            let response = try await client.previewNewsletters()
            return self.formatPreviewMessage(source: "Newsletters", response: response)
        }
    }

    func clearWallabagSeen() async {
        await runIntegrationAction {
            let client = try await self.createClient()
            let response = try await client.clearWallabagSeen()
            return "Cleared \(response.cleared) Wallabag seen markers"
        }
    }

    func clearNewslettersSeen() async {
        await runIntegrationAction {
            let client = try await self.createClient()
            let response = try await client.clearNewsletterSeen()
            return "Cleared \(response.cleared) newsletter seen markers"
        }
    }

    private func runIntegrationAction(_ operation: () async throws -> String) async {
        guard !integrationActionRunning else { return }
        integrationActionRunning = true
        defer { integrationActionRunning = false }

        do {
            integrationActionMessage = try await operation()
            await fetchIntegrationStatus()
        } catch {
            integrationActionMessage = error.localizedDescription
        }
    }

    private func updateConfigToggle(
        applyOptimistic: () -> Void,
        rollback: () -> Void,
        request: (String?) -> ClientConfigUpdateRequest
    ) async {
        guard !configActionRunning else { return }
        integrationActionMessage = nil
        applyOptimistic()
        configActionRunning = true
        defer { configActionRunning = false }

        do {
            let client = try await createClient()
            let localTimestamp = try await settingsRepository.getGhostwriterConfigUpdatedAt()
            let response = try await client.updateConfig(request(localTimestamp))
            try await settingsRepository.setGhostwriterConfigUpdatedAt(response.updatedAt)
            applyConfig(response)
        } catch GhostwriterError.conflict {
            do {
                let client = try await createClient()
                let latest = try await client.getConfig()
                try await settingsRepository.setGhostwriterConfigUpdatedAt(latest.updatedAt)
                applyConfig(latest)
                integrationActionMessage = "Config changed on server. Refreshed latest values."
            } catch {
                rollback()
                integrationActionMessage = "Config changed on server. Please retry."
            }
        } catch {
            rollback()
            integrationActionMessage = "Config update failed: \(error.localizedDescription)"
        }
    }

    private func applyConfig(_ config: ClientConfigResponse) {
        wallabagIntegration = config.wallabag
        newslettersIntegration = config.newsletters
        includePodcastsInDigest = config.includePodcastsInDigest ?? includePodcastsInDigest
        includeYoutubeInDigest = config.includeYoutubeInDigest ?? includeYoutubeInDigest
        coverEnabled = config.coverEnabled ?? coverEnabled
        coverOverlayEnabled = config.coverOverlayEnabled ?? coverOverlayEnabled
    }

    private func createClient() async throws -> GhostwriterClient {
        guard !serverURL.isEmpty else {
            throw GhostwriterError.invalidURL("Missing Ghostwriter server URL")
        }
        let apiKey = try await settingsRepository.getGhostwriterAPIKey()
        return try GhostwriterClient(baseURLString: serverURL, apiKey: apiKey)
    }

    private func formatPreviewMessage(source: String, response: PreviewResponse) -> String {
        if response.status == "ok" {
            let count = response.count ?? response.articles?.count ?? 0
            return "\(source) preview: \(count) article\(count == 1 ? "" : "s") available"
        }
        return response.detail ?? "\(source) preview failed"
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
    func getGhostwriterDownloadEpubsOnSync() async throws -> Bool { true }
    func setGhostwriterDownloadEpubsOnSync(_ enabled: Bool) async throws {}
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
}
