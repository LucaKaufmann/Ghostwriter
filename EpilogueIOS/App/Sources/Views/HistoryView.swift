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
    @State private var downloadingDigestIDs: Set<UUID> = []
    @State private var pdfDownloadsEnabled = false
    @State private var statusMessage: String?

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
                            let epubAvailable = hasLocalEPUB(digest)
                            NavigationLink {
                                DigestDetailView(digest: digest)
                            } label: {
                                DigestRow(digest: digest, epubAvailable: epubAvailable)
                            }
                            .swipeActions(edge: .trailing, allowsFullSwipe: true) {
                                Button(role: .destructive) {
                                    digestToDelete = digest
                                } label: {
                                    Label("Delete", systemImage: "trash")
                                }
                            }
                            .swipeActions(edge: .leading) {
                                if let remoteId = digest.remoteId {
                                    if pdfDownloadsEnabled {
                                        Button {
                                            downloadDigestPdf(digest, remoteId: remoteId)
                                        } label: {
                                            if downloadingDigestIDs.contains(digest.id) {
                                                Label("Downloading", systemImage: "hourglass")
                                            } else {
                                                Label("PDF", systemImage: "doc.richtext")
                                            }
                                        }
                                        .tint(.orange)
                                    }

                                    if !epubAvailable {
                                        Button {
                                            downloadDigest(digest, remoteId: remoteId)
                                        } label: {
                                            if downloadingDigestIDs.contains(digest.id) {
                                                Label("Downloading", systemImage: "hourglass")
                                            } else {
                                                Label("EPUB", systemImage: "arrow.down.circle")
                                            }
                                        }
                                        .tint(.green)
                                    } else {
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
                                } else {
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
            .task {
                pdfDownloadsEnabled = await ghostwriterCoordinator.isPdfDownloadEnabled()
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
            .alert("Digest History", isPresented: Binding(
                get: { statusMessage != nil },
                set: { if !$0 { statusMessage = nil } }
            )) {
                Button("OK", role: .cancel) {
                    statusMessage = nil
                }
            } message: {
                Text(statusMessage ?? "")
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
            if digest.remoteId != nil {
                statusMessage = "EPUB not downloaded yet. Use Download from digest history first."
            } else {
                statusMessage = "EPUB file not found."
            }
            return
        }
        UIApplication.shared.open(fileURL)
    }

    private func hasLocalEPUB(_ digest: Digest) -> Bool {
        guard !digest.epubFilePath.isEmpty else { return false }
        return FileManager.default.fileExists(atPath: digest.epubFilePath)
    }

    private func downloadDigest(_ digest: Digest, remoteId: String) {
        guard !downloadingDigestIDs.contains(digest.id) else { return }
        downloadingDigestIDs.insert(digest.id)

        Task { @MainActor in
            defer { downloadingDigestIDs.remove(digest.id) }

            let filenameHint: String? = {
                guard !digest.epubFilePath.isEmpty else { return nil }
                let name = URL(fileURLWithPath: digest.epubFilePath).lastPathComponent
                return name.hasSuffix(".epub") ? name : nil
            }()

            do {
                let localURL = try await ghostwriterCoordinator.downloadDigestEpub(
                    remoteId: remoteId,
                    filenameHint: filenameHint
                )
                digest.epubFilePath = localURL.path
                if let attributes = try? FileManager.default.attributesOfItem(atPath: localURL.path),
                   let fileSize = attributes[.size] as? NSNumber {
                    digest.fileSizeBytes = fileSize.int64Value
                }
                try? modelContext.save()
            } catch {
                statusMessage = "Download failed: \(error.localizedDescription)"
            }
        }
    }

    private func downloadDigestPdf(_ digest: Digest, remoteId: String) {
        guard !downloadingDigestIDs.contains(digest.id) else { return }
        downloadingDigestIDs.insert(digest.id)

        Task { @MainActor in
            defer { downloadingDigestIDs.remove(digest.id) }

            let filenameHint: String? = {
                guard !digest.epubFilePath.isEmpty else { return nil }
                let name = URL(fileURLWithPath: digest.epubFilePath).lastPathComponent
                return name.hasSuffix(".epub") ? name : nil
            }()

            do {
                let localURL = try await ghostwriterCoordinator.downloadDigestPdf(
                    remoteId: remoteId,
                    filenameHint: filenameHint
                )
                UIApplication.shared.open(localURL)
            } catch {
                statusMessage = "PDF download failed: \(error.localizedDescription)"
            }
        }
    }

}

struct DigestRow: View {
    let digest: Digest
    let epubAvailable: Bool

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

                if digest.remoteId != nil, !epubAvailable {
                    Text("EPUB not downloaded")
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
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
