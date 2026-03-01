//
//  DigestGenerator.swift
//  Epilogue
//
//  Created on 2026-01-26.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import Foundation
import SwiftData
import Domain

/// Service that orchestrates the complete digest generation process
public final class DigestGenerator {
    private let feedRepository: FeedRepositoryProtocol
    private let digestRepository: DigestRepositoryProtocol
    private let articleRepository: ArticleRepositoryProtocol
    private let epubBuilder: EPUBBuilderProtocol
    private let documentsDirectory: URL

    public init(
        feedRepository: FeedRepositoryProtocol,
        digestRepository: DigestRepositoryProtocol,
        articleRepository: ArticleRepositoryProtocol,
        epubBuilder: EPUBBuilderProtocol,
        documentsDirectory: URL? = nil
    ) {
        self.feedRepository = feedRepository
        self.digestRepository = digestRepository
        self.articleRepository = articleRepository
        self.epubBuilder = epubBuilder

        // Default to app's Documents/Epilogue directory
        if let documentsDir = documentsDirectory {
            self.documentsDirectory = documentsDir
        } else {
            let appDocs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first!
            self.documentsDirectory = appDocs.appendingPathComponent("Epilogue")
        }
    }

    /// Generate a new digest from all enabled feeds.
    /// - Parameters:
    ///   - triggerType: How the generation was initiated.
    ///   - period: Optional digest period label (e.g. MORNING/NOON/EVENING/manual).
    public func generateDigest(triggerType: TriggerType, period: String? = nil) async throws -> Digest {
        // Create Documents/Epilogue directory if needed
        try createDocumentsDirectory()

        // Create digest record
        let date = Date()
        let epubFileName = generateFileName(for: date, period: period)
        let epubFilePath = documentsDirectory.appendingPathComponent(epubFileName).path

        let digest = Digest(
            generatedAt: date,
            epubFilePath: epubFilePath,
            triggerType: triggerType,
            isComplete: false,
            period: period
        )

        // Save initial digest
        try await digestRepository.createDigest(digest)

        do {
            // Fetch enabled feeds
            let feeds = try await feedRepository.getEnabledFeeds()

            guard !feeds.isEmpty else {
                throw DigestGeneratorError.noEnabledFeeds
            }

            // Process all feeds in parallel
            let allArticles = try await withThrowingTaskGroup(of: [ProcessedArticle].self) { group in
                for feed in feeds {
                    group.addTask {
                        (try? await self.articleRepository.fetchAndProcessArticles(from: feed)) ?? []
                    }
                }

                var articles: [ProcessedArticle] = []
                for try await feedArticles in group {
                    articles.append(contentsOf: feedArticles)
                }
                return articles
            }

            let feedOrder = Dictionary(
                uniqueKeysWithValues: feeds.enumerated().map { index, feed in
                    (feed.url, index)
                }
            )
            let orderedArticles = allArticles.enumerated().sorted { lhs, rhs in
                let lhsOrder = feedOrder[lhs.element.feedUrl] ?? Int.max
                let rhsOrder = feedOrder[rhs.element.feedUrl] ?? Int.max
                if lhsOrder != rhsOrder {
                    return lhsOrder < rhsOrder
                }
                return lhs.offset < rhs.offset
            }.map(\.element)

            guard !orderedArticles.isEmpty else {
                throw DigestGeneratorError.noArticlesFound
            }

            // Generate EPUB
            let epubURL = try epubBuilder.generateEPUB(
                articles: orderedArticles,
                outputPath: epubFilePath,
                date: date
            )

            // Get file size
            let attributes = try FileManager.default.attributesOfItem(atPath: epubURL.path)
            let fileSize = attributes[.size] as? Int64 ?? 0

            // Count article types
            let briefings = orderedArticles.filter { $0.isSummary }
            let deepDives = orderedArticles.filter { !$0.isSummary }

            // Update digest with results
            digest.isComplete = true
            digest.articleCount = orderedArticles.count
            digest.briefingCount = briefings.count
            digest.deepDiveCount = deepDives.count
            digest.fileSizeBytes = fileSize
            digest.errorMessage = nil

            // Create digest articles
            var digestArticles: [DigestArticle] = []

            for (index, article) in orderedArticles.enumerated() {
                let contentType: ContentType = article.isSummary ? .briefing : .deepDive
                let digestArticle = article.toDigestArticle(
                    contentType: contentType,
                    orderIndex: index
                )
                digestArticle.digest = digest
                digestArticles.append(digestArticle)
            }

            digest.articles = digestArticles

            try await digestRepository.updateDigest(digest)

            return digest

        } catch {
            // Update digest with error
            digest.isComplete = false
            digest.errorMessage = error.localizedDescription
            try await digestRepository.updateDigest(digest)
            throw error
        }
    }

    // MARK: - Private Helpers

    private func createDocumentsDirectory() throws {
        let fileManager = FileManager.default
        if !fileManager.fileExists(atPath: documentsDirectory.path) {
            try fileManager.createDirectory(
                at: documentsDirectory,
                withIntermediateDirectories: true
            )
        }
    }

    private func generateFileName(for date: Date, period: String?) -> String {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd_HHmmss"
        let dateString = formatter.string(from: date)

        if let period {
            let slug = period.lowercased().filter { $0.isLetter || $0.isNumber || $0 == "-" }
            if !slug.isEmpty {
                return "Epilogue_\(dateString)_\(slug).epub"
            }
        }
        return "Epilogue_\(dateString).epub"
    }
}

// MARK: - Errors

public enum DigestGeneratorError: LocalizedError {
    case noEnabledFeeds
    case noArticlesFound

    public var errorDescription: String? {
        switch self {
        case .noEnabledFeeds:
            return "No enabled feeds found"
        case .noArticlesFound:
            return "No articles could be fetched from enabled feeds"
        }
    }
}
