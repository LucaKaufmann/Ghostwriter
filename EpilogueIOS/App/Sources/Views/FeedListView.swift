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

struct FeedListView: View {
    @Environment(\.modelContext) private var modelContext
    @EnvironmentObject private var ghostwriterCoordinator: GhostwriterSyncCoordinator
    @Query(
        filter: #Predicate<Feed> { !$0.url.starts(with: "synthetic://") },
        sort: \Feed.createdAt,
        order: .reverse
    ) private var feeds: [Feed]
    @State private var showingAddFeed = false
    @State private var editingFeed: Feed?

    var body: some View {
        NavigationStack {
            Group {
                if feeds.isEmpty {
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
                        ForEach(feeds) { feed in
                            FeedRow(feed: feed)
                                .contentShape(Rectangle())
                                .onTapGesture {
                                    editingFeed = feed
                                }
                        }
                        .onDelete(perform: deleteFeeds)
                    }
                }
            }
            .navigationTitle("Feed Manager")
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    SyncStatusBanner(coordinator: ghostwriterCoordinator)
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button(action: { showingAddFeed = true }) {
                        Image(systemName: "plus")
                    }
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
        }
    }

    private func deleteFeeds(at offsets: IndexSet) {
        let deletedURLs = offsets.map { feeds[$0].url }

        for index in offsets {
            modelContext.delete(feeds[index])
        }
        try? modelContext.save()

        Task {
            for url in deletedURLs {
                try? await ghostwriterCoordinator.notifyFeedDeleted(url: url)
            }
        }
    }
}

struct FeedRow: View {
    let feed: Feed

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(feed.name)
                .font(.headline)
            Text(feed.url)
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(1)
            HStack(spacing: 8) {
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
    @Environment(\.modelContext) private var modelContext

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
                    Button("Add") {
                        addFeed()
                        dismiss()
                    }
                    .disabled(url.isEmpty || name.isEmpty)
                }
            }
        }
    }

    private func addFeed() {
        let feed = Feed(
            url: url.trimmingCharacters(in: .whitespacesAndNewlines),
            name: name.trimmingCharacters(in: .whitespacesAndNewlines),
            mode: mode,
            maxArticles: Int(maxArticles),
            isEnabled: isEnabled
        )
        modelContext.insert(feed)
        try? modelContext.save()
    }
}

struct EditFeedView: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(\.modelContext) private var modelContext

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
                    Button("Save") {
                        saveFeed()
                        dismiss()
                    }
                    .disabled(name.isEmpty)
                }
            }
        }
    }

    private func saveFeed() {
        feed.name = name.trimmingCharacters(in: .whitespacesAndNewlines)
        feed.mode = mode
        feed.isEnabled = isEnabled
        feed.maxArticles = Int(maxArticles)
        try? modelContext.save()
    }
}
