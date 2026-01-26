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

    /// Generate a new digest from all enabled feeds
    public func generateDigest(triggerType: TriggerType) async throws -> Digest {
        // Create Documents/Epilogue directory if needed
        try createDocumentsDirectory()

        // Create digest record
        let date = Date()
        let epubFileName = generateFileName(for: date)
        let epubFilePath = documentsDirectory.appendingPathComponent(epubFileName).path

        let digest = Digest(
            generatedAt: date,
            epubFilePath: epubFilePath,
            triggerType: triggerType,
            isComplete: false
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

            guard !allArticles.isEmpty else {
                throw DigestGeneratorError.noArticlesFound
            }

            // Generate EPUB
            let epubURL = try epubBuilder.generateEPUB(
                articles: allArticles,
                outputPath: epubFilePath,
                date: date
            )

            // Get file size
            let attributes = try FileManager.default.attributesOfItem(atPath: epubURL.path)
            let fileSize = attributes[.size] as? Int64 ?? 0

            // Count article types
            let briefings = allArticles.filter { $0.isSummary }
            let deepDives = allArticles.filter { !$0.isSummary }

            // Update digest with results
            digest.isComplete = true
            digest.articleCount = allArticles.count
            digest.briefingCount = briefings.count
            digest.deepDiveCount = deepDives.count
            digest.fileSizeBytes = fileSize
            digest.errorMessage = nil

            // Create digest articles
            var digestArticles: [DigestArticle] = []

            for (index, article) in briefings.enumerated() {
                let digestArticle = article.toDigestArticle(
                    contentType: .briefing,
                    orderIndex: index
                )
                digestArticle.digest = digest
                digestArticles.append(digestArticle)
            }

            for (index, article) in deepDives.enumerated() {
                let digestArticle = article.toDigestArticle(
                    contentType: .deepDive,
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

    private func generateFileName(for date: Date) -> String {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        let dateString = formatter.string(from: date)
        return "Epilogue_\(dateString).epub"
    }
}

// MARK: - Protocol

public protocol EPUBBuilderProtocol: Sendable {
    func generateEPUB(
        articles: [ProcessedArticle],
        outputPath: String,
        date: Date
    ) throws -> URL
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
