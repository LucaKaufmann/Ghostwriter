//
//  CustomExportHelper.swift
//  Epilogue
//
//  Handles exporting EPUBs to a user-selected folder via security-scoped bookmarks.
//

import Foundation
import Domain
import OSLog

enum CustomExportHelper {
    private static let logger = Logger(subsystem: "com.epilogue", category: "CustomExport")

    static func exportIfConfigured(
        fileURL: URL,
        settingsRepository: SettingsRepositoryProtocol
    ) async {
        do {
            guard try await settingsRepository.getCustomExportEnabled() else { return }
            guard let bookmark = try await settingsRepository.getCustomExportBookmark() else { return }

            var isStale = false
            let directoryURL = try URL(
                resolvingBookmarkData: bookmark,
                options: [.withSecurityScope],
                relativeTo: nil,
                bookmarkDataIsStale: &isStale
            )

            let didAccess = directoryURL.startAccessingSecurityScopedResource()
            defer {
                if didAccess {
                    directoryURL.stopAccessingSecurityScopedResource()
                }
            }

            if isStale {
                let refreshed = try directoryURL.bookmarkData(options: [.withSecurityScope])
                try await settingsRepository.setCustomExportBookmark(refreshed)
            }

            let destinationURL = directoryURL.appendingPathComponent(fileURL.lastPathComponent)
            if FileManager.default.fileExists(atPath: destinationURL.path) {
                try FileManager.default.removeItem(at: destinationURL)
            }

            try FileManager.default.copyItem(at: fileURL, to: destinationURL)
            logger.info("Exported EPUB to \(destinationURL.path, privacy: .public)")
        } catch {
            logger.error("Custom export failed: \(error.localizedDescription, privacy: .public)")
        }
    }
}
