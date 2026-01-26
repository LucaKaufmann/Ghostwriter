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
    @Query(sort: \Feed.createdAt, order: .reverse) private var feeds: [Feed]
    @State private var showingAddFeed = false

    var body: some View {
        NavigationStack {
            List {
                ForEach(feeds) { feed in
                    FeedRow(feed: feed)
                }
            }
            .navigationTitle("Feeds")
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button(action: { showingAddFeed = true }) {
                        Image(systemName: "plus")
                    }
                }
            }
            .sheet(isPresented: $showingAddFeed) {
                AddFeedView()
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
            HStack {
                Text(feed.mode.displayName)
                    .font(.caption)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(Color.black.opacity(0.1))
                    .cornerRadius(4)
                Text("\(feed.isEnabled ? "Enabled" : "Disabled")")
                    .font(.caption)
                    .foregroundStyle(feed.isEnabled ? .green : .red)
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
    @State private var mode: ProcessingMode = .briefing
    @State private var maxArticles = 10

    var body: some View {
        NavigationStack {
            Form {
                Section("Feed Details") {
                    TextField("Feed URL", text: $url)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    TextField("Name", text: $name)
                }

                Section("Processing") {
                    Picker("Mode", selection: $mode) {
                        ForEach(ProcessingMode.allCases, id: \.self) { mode in
                            Text(mode.displayName).tag(mode)
                        }
                    }
                    Stepper("Max Articles: \(maxArticles)", value: $maxArticles, in: 1...50)
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
        let feed = Feed(url: url, name: name, mode: mode, maxArticles: maxArticles)
        modelContext.insert(feed)
        try? modelContext.save()
    }
}
