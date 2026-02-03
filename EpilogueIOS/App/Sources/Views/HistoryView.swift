//
//  HistoryView.swift
//  Epilogue
//
//  Created on 2026-01-26.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import SwiftUI
import UIKit
import SwiftData
import Domain

struct HistoryView: View {
    @Environment(\.modelContext) private var modelContext
    @EnvironmentObject private var ghostwriterCoordinator: GhostwriterSyncCoordinator
    @Query(sort: \Digest.generatedAt, order: .reverse) private var digests: [Digest]
    @State private var digestToDelete: Digest?
    @State private var digestToShare: Digest?

    var body: some View {
        NavigationStack {
            Group {
                if digests.isEmpty {
                    // Empty state matching Android
                    VStack(spacing: 8) {
                        Spacer()
                        Text("No digests yet")
                            .font(.title2)
                        Text("Generate your first digest from Settings")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                        Spacer()
                    }
                } else {
                    List {
                        ForEach(digests) { digest in
                            NavigationLink {
                                DigestDetailView(digest: digest)
                            } label: {
                                DigestRow(digest: digest)
                            }
                            .swipeActions(edge: .trailing, allowsFullSwipe: true) {
                                Button(role: .destructive) {
                                    digestToDelete = digest
                                } label: {
                                    Label("Delete", systemImage: "trash")
                                }
                            }
                            .swipeActions(edge: .leading) {
                                Button {
                                    digestToShare = digest
                                } label: {
                                    Label("Share", systemImage: "square.and.arrow.up")
                                }
                                .tint(.gray)

                                Button {
                                    openInReader(digest)
                                } label: {
                                    Label("Open", systemImage: "book")
                                }
                                .tint(.blue)
                            }
                        }
                    }
                }
            }
            .navigationTitle("Digest History")
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    SyncStatusBanner(coordinator: ghostwriterCoordinator)
                }
            }
            .refreshable {
                await ghostwriterCoordinator.performFullSyncIncludingDigests()
            }
            .alert("Delete Digest?", isPresented: Binding(
                get: { digestToDelete != nil },
                set: { if !$0 { digestToDelete = nil } }
            )) {
                Button("Cancel", role: .cancel) {
                    digestToDelete = nil
                }
                Button("Delete", role: .destructive) {
                    if let digest = digestToDelete {
                        deleteDigest(digest)
                    }
                    digestToDelete = nil
                }
            } message: {
                Text("This will permanently delete this digest and its EPUB file.")
            }
            .sheet(isPresented: Binding(
                get: { digestToShare != nil },
                set: { if !$0 { digestToShare = nil } }
            )) {
                if let digest = digestToShare {
                    let fileURL = URL(fileURLWithPath: digest.epubFilePath)
                    ActivityViewController(activityItems: [fileURL])
                }
            }
        }
    }

    private func deleteDigest(_ digest: Digest) {
        // Delete EPUB file from disk
        let fileURL = URL(fileURLWithPath: digest.epubFilePath)
        try? FileManager.default.removeItem(at: fileURL)

        // Delete from database
        modelContext.delete(digest)
        try? modelContext.save()
    }

    private func openInReader(_ digest: Digest) {
        let fileURL = URL(fileURLWithPath: digest.epubFilePath)
        guard FileManager.default.fileExists(atPath: fileURL.path) else {
            return
        }
        UIApplication.shared.open(fileURL)
    }

}

struct DigestRow: View {
    let digest: Digest

    private var dateFormatter: DateFormatter {
        let formatter = DateFormatter()
        formatter.dateFormat = "MMM d, yyyy"
        return formatter
    }

    private var periodLabel: String {
        guard let period = digest.period, !period.isEmpty else { return "" }
        switch period {
        case "morning": return " Morning"
        case "noon": return " Noon"
        case "evening": return " Evening"
        case "manual": return " Manual"
        default: return " \(period.capitalized)"
        }
    }

    private var timeFormatter: DateFormatter {
        let formatter = DateFormatter()
        formatter.dateFormat = "HH:mm"
        return formatter
    }

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                // Date
                Text(dateFormatter.string(from: digest.generatedAt))
                    .font(.headline)

                // Time, period, and trigger type
                Text("\(timeFormatter.string(from: digest.generatedAt))\(periodLabel) - \(digest.triggerType.displayName)")
                    .font(.caption)
                    .foregroundStyle(.secondary)

                // Article counts matching Android format
                Text("\(digest.articleCount) articles (\(digest.briefingCount) briefings, \(digest.deepDiveCount) full)")
                    .font(.caption)

                // Feed names (if available from articles)
                if !digest.articles.isEmpty {
                    let feedNames = Array(Set(digest.articles.map { $0.feedName }))
                    let feedText = feedNames.count <= 3
                        ? feedNames.joined(separator: ", ")
                        : feedNames.prefix(3).joined(separator: ", ") + " +\(feedNames.count - 3) more"
                    Text(feedText)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
            }
        }
        .padding(.vertical, 4)
    }
}

// MARK: - UIKit Share Sheet Wrapper

private struct ActivityViewController: UIViewControllerRepresentable {
    let activityItems: [Any]

    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: activityItems, applicationActivities: nil)
    }

    func updateUIViewController(_ uiViewController: UIActivityViewController, context: Context) {}
}
