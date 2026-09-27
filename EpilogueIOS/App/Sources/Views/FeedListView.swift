//
//  FeedListView.swift
//  Epilogue
//
//  Created on 2026-01-26.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import SwiftUI
import SwiftData
import Domain
import GhostwriterClient

struct FeedListView: View {
    @EnvironmentObject private var ghostwriterCoordinator: GhostwriterSyncCoordinator
    @Query(sort: \Feed.createdAt, order: .reverse) private var allFeeds: [Feed]
    @Query(sort: \FeedMutation.sequence) private var mutations: [FeedMutation]
    @Query private var syncStates: [FeedSyncState]

    private var currentScope: String? {
        guard let state = syncStates.first,
              let url = state.destinationURL,
              let configurationId = state.configurationId else { return nil }
        return url + "\n" + configurationId
    }

    private var previousMutations: [FeedMutation] {
        guard let currentScope else { return [] }
        var seen = Set<String>()
        return mutations.filter { mutation in
            guard mutation.scopeKey != currentScope,
                  mutation.scopeKey != "__unbound__" else { return false }
            return seen.insert(mutation.scopeKey + "\n" + mutation.url).inserted
        }
    }
    
    static func partition(_ allFeeds: [Feed], mutations: [FeedMutation],
                          currentScope: String? = nil)
        -> (visible: [Feed], attention: [Feed]) {
        let ordinary = allFeeds.filter { !$0.url.hasPrefix("synthetic://") }
        return (
            ordinary.filter { $0.isLocallyDeleted != true },
            ordinary.filter { feed in
                feed.isLocallyDeleted == true && mutations.contains {
                    $0.url == feed.url &&
                    (currentScope == nil || $0.scopeKey == currentScope) &&
                    ["needs_resolution", "conflict", "rejected"].contains($0.status)
                }
            }
        )
    }

    /// Normal feed rows exclude local deletes and acknowledged tombstones.
    private var feeds: [Feed] {
        Self.partition(allFeeds, mutations: mutations, currentScope: currentScope).visible
    }
    private var attentionFeeds: [Feed] {
        Self.partition(allFeeds, mutations: mutations, currentScope: currentScope).attention
    }
    @State private var showingAddFeed = false
    @State private var editingFeed: Feed?
    @State private var resolvingMutation: FeedMutation?
    @State private var previousMutation: FeedMutation?
    @State private var errorMessage: String?
    @State private var showingOlderServerFeeds = false

    private var olderServerNeedsPreview: Bool {
        ghostwriterCoordinator.requiresOlderServerFeedPreview
    }

    var body: some View {
        NavigationStack {
            Group {
                if feeds.isEmpty && attentionFeeds.isEmpty && previousMutations.isEmpty {
                    // Empty state matching Android
                    VStack(spacing: 8) {
                        Spacer()
                        Text("No feeds added yet")
                            .font(.body)
                        Text("Tap + to add your first RSS feed")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                        Spacer()
                    }
                } else {
                    List {
                        Section("Feeds") {
                            ForEach(feeds) { feed in
                                feedRow(feed)
                            }
                            .onDelete(perform: deleteFeeds)
                        }
                        if !attentionFeeds.isEmpty {
                            Section("Needs attention") {
                                ForEach(attentionFeeds) { feed in
                                    feedRow(feed)
                                }
                            }
                        }
                        if !previousMutations.isEmpty {
                            Section("Saved edits from previous server") {
                                ForEach(previousMutations) { mutation in
                                    Button {
                                        previousMutation = mutation
                                    } label: {
                                        VStack(alignment: .leading) {
                                            Text(mutation.title ?? mutation.url)
                                            Text(mutation.url)
                                                .font(.caption).foregroundStyle(.secondary)
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
            .navigationTitle("Feed Manager")
            .toolbar {
                if olderServerNeedsPreview {
                    ToolbarItem(placement: .navigationBarLeading) {
                        Button("Older server feeds") { showingOlderServerFeeds = true }
                    }
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    SyncStatusBanner(coordinator: ghostwriterCoordinator)
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button(action: { showingAddFeed = true }) {
                        Image(systemName: "plus")
                    }
                    .accessibilityLabel("Add feed")
                }
            }
            .refreshable {
                await ghostwriterCoordinator.performFullSync()
            }
            .sheet(isPresented: $showingAddFeed) {
                AddFeedView()
            }
            .sheet(item: $editingFeed) { feed in
                EditFeedView(feed: feed)
            }
            .sheet(item: $resolvingMutation) { mutation in
                FeedResolutionView(mutation: mutation)
            }
            .sheet(item: $previousMutation) { mutation in
                PreviousFeedProposalView(mutation: mutation)
            }
            .sheet(isPresented: $showingOlderServerFeeds) {
                OlderServerFeedPreviewView()
            }
            .alert("Feed change failed", isPresented: Binding(
                get: { errorMessage != nil }, set: { if !$0 { errorMessage = nil } }
            )) { Button("OK", role: .cancel) { errorMessage = nil } } message: {
                Text(errorMessage ?? "Unknown error")
            }
        }
    }

    private func feedRow(_ feed: Feed) -> some View {
        FeedRow(feed: feed, issue: currentIssue(for: feed.url))
        .contentShape(Rectangle())
        .onTapGesture {
            if let issue = currentIssue(for: feed.url) {
                resolvingMutation = issue
            } else if feed.isLocallyDeleted != true {
                editingFeed = feed
            }
        }
    }

    private func currentIssue(for url: String) -> FeedMutation? {
        mutations.first {
            $0.url == url &&
            (currentScope == nil || $0.scopeKey == currentScope) &&
            ["needs_resolution", "conflict", "rejected"].contains($0.status)
        }
    }

    private func deleteFeeds(at offsets: IndexSet) {
        do {
            for index in offsets {
                try ghostwriterCoordinator.deleteFeed(url: feeds[index].url)
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

private struct OlderServerFeedPreviewView: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var coordinator: GhostwriterSyncCoordinator
    @State private var rows: [FeedResponse] = []
    @State private var error: String?

    var body: some View {
        NavigationStack {
            List {
                Section {
                    ForEach(rows) { row in
                        VStack(alignment: .leading) {
                            Text(row.title)
                            Text(row.url).font(.caption).foregroundStyle(.secondary)
                        }
                    }
                } footer: {
                    Text("This is a read-only view of the older server. Your saved feed edits remain on this device until feed sync is available.")
                }
                if let error { Text(error).foregroundStyle(.red) }
            }
            .navigationTitle("Older server feeds")
            .toolbar { Button("Done") { dismiss() } }
            .task {
                do { rows = try await coordinator.previewOlderServerFeeds() }
                catch { self.error = error.localizedDescription }
            }
        }
    }
}

private enum FeedSyncDisplay {
    static func mode(_ value: String?, fallback: String = "Unchanged") -> String {
        guard let value else { return fallback }
        return value == "summarize" ? "Briefing" : "Fidelity"
    }

    static func enabled(_ value: Bool?, fallback: String = "Unchanged") -> String {
        guard let value else { return fallback }
        return value ? "Enabled" : "Paused"
    }

    static func maximum(_ value: Int?, fallback: String = "Unchanged") -> String {
        guard let value else { return fallback }
        return value == 0 ? "Unlimited" : String(value)
    }
}

private struct PreviousFeedProposalView: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var coordinator: GhostwriterSyncCoordinator
    let mutation: FeedMutation
    @State private var errorMessage: String?

    var body: some View {
        NavigationStack {
            Form {
                Section("Saved proposal") {
                    LabeledContent("Feed", value: mutation.url)
                    LabeledContent("Change", value: mutation.kind == "delete" ? "Remove feed" : "Edit feed")
                    if let title = mutation.title { LabeledContent("Title", value: title) }
                    if let mode = mutation.mode {
                        LabeledContent("Mode", value: FeedSyncDisplay.mode(mode))
                    }
                    if let enabled = mutation.isActive {
                        LabeledContent("Status", value: FeedSyncDisplay.enabled(enabled))
                    }
                    if let maximum = mutation.maxArticles {
                        LabeledContent("Maximum", value: FeedSyncDisplay.maximum(maximum))
                    }
                }
                Section {
                    Button("Apply to current server") { resolve(.transfer) }
                    Button("Discard saved proposal", role: .destructive) { resolve(.discard) }
                } footer: {
                    Text("Applying creates a new change for this server. The saved operation will never be replayed automatically.")
                }
            }
            .navigationTitle("Previous server edit")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Close") { dismiss() } }
            }
            .alert("Could not resolve saved edit", isPresented: Binding(
                get: { errorMessage != nil }, set: { if !$0 { errorMessage = nil } }
            )) { Button("OK", role: .cancel) { errorMessage = nil } } message: {
                Text(errorMessage ?? "Unknown error")
            }
        }
    }

    private func resolve(_ action: IOSFeedV2StoreEngine.PreviousProposalAction) {
        Task { @MainActor in
            do {
                try await coordinator.resolvePreviousFeedProposal(opId: mutation.opId, action: action)
                dismiss()
            } catch {
                errorMessage = error.localizedDescription
            }
        }
    }
}

struct FeedRow: View {
    let feed: Feed
    let issue: FeedMutation?

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(feed.name)
                .font(.headline)
            Text(feed.url)
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(1)
            HStack(spacing: 8) {
                if feed.isLocallyDeleted == true {
                    Text(issue?.serverKind == nil && issue?.kind != "delete"
                         ? "Not on server" : "Removed locally")
                        .font(.caption)
                }
                if let issue {
                    Text(issue.status == "rejected" ? "Rejected" : "Needs resolution")
                        .font(.caption).foregroundStyle(.orange)
                }
                if !feed.isEnabled {
                    Text("Paused")
                        .font(.caption)
                }
                Text(feed.mode == .fidelity ? "Fidelity" : "Briefing")
                    .font(.caption)
                if feed.maxArticles > 0 {
                    Text("Max: \(feed.maxArticles)")
                        .font(.caption)
                }
            }
        }
        .padding(.vertical, 4)
    }
}

struct AddFeedView: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var ghostwriterCoordinator: GhostwriterSyncCoordinator
    @State private var errorMessage: String?

    @State private var url = ""
    @State private var name = ""
    @State private var mode: ProcessingMode = .fidelity
    @State private var isEnabled = true
    @State private var maxArticles: Double = 0

    var body: some View {
        NavigationStack {
            Form {
                Section("Feed Details") {
                    TextField("Feed URL", text: $url)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    TextField("Nickname", text: $name)
                }

                Section("Processing Mode") {
                    Picker("Mode", selection: $mode) {
                        Text("Fidelity").tag(ProcessingMode.fidelity)
                        Text("Briefing").tag(ProcessingMode.briefing)
                    }
                    .pickerStyle(.segmented)
                }

                Section("State") {
                    Toggle("Enabled", isOn: $isEnabled)
                }

                Section {
                    VStack(alignment: .leading, spacing: 8) {
                        HStack {
                            Text("Max articles")
                            Spacer()
                            Text(maxArticles == 0 ? "Unlimited" : "\(Int(maxArticles))")
                                .foregroundStyle(.secondary)
                        }
                        Slider(value: $maxArticles, in: 0...50, step: 5)
                    }
                }
            }
            .navigationTitle("Add Feed")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Add") { addFeed() }
                    .disabled(url.isEmpty || name.isEmpty)
                }
            }
            .alert("Could not add feed", isPresented: Binding(
                get: { errorMessage != nil }, set: { if !$0 { errorMessage = nil } }
            )) { Button("OK", role: .cancel) { errorMessage = nil } } message: {
                Text(errorMessage ?? "Unknown error")
            }
        }
    }

    private func addFeed() {
        do {
            try ghostwriterCoordinator.addOrEditFeed(
                url: url.trimmingCharacters(in: .whitespacesAndNewlines),
                title: name.trimmingCharacters(in: .whitespacesAndNewlines),
                mode: mode,
                isEnabled: isEnabled,
                maxArticles: Int(maxArticles))
            dismiss()
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

struct EditFeedView: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var ghostwriterCoordinator: GhostwriterSyncCoordinator
    @State private var errorMessage: String?

    let feed: Feed

    @State private var name: String
    @State private var mode: ProcessingMode
    @State private var isEnabled: Bool
    @State private var maxArticles: Double

    init(feed: Feed) {
        self.feed = feed
        _name = State(initialValue: feed.name)
        _mode = State(initialValue: feed.mode)
        _isEnabled = State(initialValue: feed.isEnabled)
        _maxArticles = State(initialValue: Double(feed.maxArticles))
    }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Text(feed.url)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Section("Feed Details") {
                    TextField("Nickname", text: $name)
                }

                Section("Processing Mode") {
                    Picker("Mode", selection: $mode) {
                        Text("Fidelity").tag(ProcessingMode.fidelity)
                        Text("Briefing").tag(ProcessingMode.briefing)
                    }
                    .pickerStyle(.segmented)
                }

                Section("State") {
                    Toggle("Enabled", isOn: $isEnabled)
                }

                Section {
                    VStack(alignment: .leading, spacing: 8) {
                        HStack {
                            Text("Max articles")
                            Spacer()
                            Text(maxArticles == 0 ? "Unlimited" : "\(Int(maxArticles))")
                                .foregroundStyle(.secondary)
                        }
                        Slider(value: $maxArticles, in: 0...50, step: 5)
                    }
                }
            }
            .navigationTitle("Edit Feed")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") { saveFeed() }
                    .disabled(name.isEmpty)
                }
            }
            .alert("Could not save feed", isPresented: Binding(
                get: { errorMessage != nil }, set: { if !$0 { errorMessage = nil } }
            )) { Button("OK", role: .cancel) { errorMessage = nil } } message: {
                Text(errorMessage ?? "Unknown error")
            }
        }
    }

    private func saveFeed() {
        do {
            try ghostwriterCoordinator.addOrEditFeed(
                url: feed.url,
                title: name.trimmingCharacters(in: .whitespacesAndNewlines),
                mode: mode, isEnabled: isEnabled, maxArticles: Int(maxArticles))
            dismiss()
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

struct FeedResolutionView: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var coordinator: GhostwriterSyncCoordinator
    let mutation: FeedMutation
    @State private var correctedTitle = ""
    @State private var errorMessage: String?

    private var absent: Bool { mutation.serverKind == nil }

    var body: some View {
        NavigationStack {
            Form {
                Section("Local proposal") {
                    LabeledContent("Feed", value: mutation.url)
                    if mutation.kind == "delete" {
                        Text("Remove this feed")
                    } else {
                        LabeledContent("Title", value: mutation.title ?? "Unchanged")
                        LabeledContent("Mode", value: FeedSyncDisplay.mode(mutation.mode))
                        LabeledContent("Status", value: FeedSyncDisplay.enabled(mutation.isActive))
                        LabeledContent("Maximum", value: FeedSyncDisplay.maximum(mutation.maxArticles))
                    }
                }
                Section("Server") {
                    if absent {
                        Text("This feed is not present on the server. It may have been removed before this device upgraded.")
                    } else if mutation.serverKind == "tombstone" {
                        Text("This feed was removed on the server.")
                    } else {
                        LabeledContent("Title", value: mutation.serverTitle ?? "")
                        LabeledContent("Mode", value: FeedSyncDisplay.mode(mutation.serverMode, fallback: ""))
                        LabeledContent("Status", value: FeedSyncDisplay.enabled(mutation.serverIsActive, fallback: ""))
                        LabeledContent("Maximum", value: FeedSyncDisplay.maximum(mutation.serverMaxArticles, fallback: ""))
                    }
                }
                if mutation.status == "rejected" {
                    Section("Rejected") {
                        Text(mutation.rejectionMessage ?? mutation.rejectionCode ?? "The server rejected this change.")
                        if mutation.kind != "delete", mutation.rejectionCode == "invalid_url" {
                            Text("This proposal cannot change its URL. Discard it, then add the feed again with a corrected URL.")
                                .foregroundStyle(.secondary)
                        } else if mutation.kind != "delete" {
                            TextField("Corrected title", text: $correctedTitle)
                            Button("Correct and retry") { resolve(.correct, title: correctedTitle) }
                        }
                        Button("Discard proposal", role: .destructive) { resolve(.discard) }
                    }
                } else if absent {
                    Section("Choose what to keep") {
                        Button("Keep removed") { resolve(.keepRemoved) }
                        Button("Add to server") { resolve(.addToServer) }
                    }
                } else if mutation.kind == "delete" {
                    Section("Choose what to keep") {
                        Button("Keep feed") { resolve(.keepServer) }
                        Button("Delete anyway", role: .destructive) { resolve(.applyMine) }
                    }
                } else {
                    Section("Choose what to keep") {
                        Button("Keep server") { resolve(.keepServer) }
                        Button("Apply mine") { resolve(.applyMine) }
                    }
                }
            }
            .navigationTitle("Resolve feed")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Close") { dismiss() }
                }
            }
            .alert("Could not resolve feed", isPresented: Binding(
                get: { errorMessage != nil }, set: { if !$0 { errorMessage = nil } }
            )) { Button("OK", role: .cancel) { errorMessage = nil } } message: {
                Text(errorMessage ?? "Unknown error")
            }
        }
    }

    private func resolve(_ action: IOSFeedV2StoreEngine.Resolution, title: String? = nil) {
        Task { @MainActor in
            do {
                try await coordinator.resolveFeed(opId: mutation.opId, action: action,
                                                  correctedTitle: title)
                dismiss()
            } catch {
                errorMessage = error.localizedDescription
            }
        }
    }
}
