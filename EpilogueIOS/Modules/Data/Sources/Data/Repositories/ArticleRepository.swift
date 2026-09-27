//
//  ArticleRepository.swift
//  Epilogue
//
//  Created on 2026-01-26.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import Foundation
import Domain
import GhostwriterClient

/// Implementation of ArticleRepositoryProtocol that orchestrates feed parsing,
/// content extraction, and AI summarization
public final class ArticleRepository: ArticleRepositoryProtocol {
    private let feedParser: FeedParserProtocol
    private let contentExtractor: ContentExtractorProtocol
    private let feedRepository: FeedRepositoryProtocol?
    private let aiService: AIServiceProtocol?
    private let minWordCount: Int

    public init(
        feedParser: FeedParserProtocol,
        contentExtractor: ContentExtractorProtocol,
        feedRepository: FeedRepositoryProtocol? = nil,
        aiService: AIServiceProtocol? = nil,
        minWordCount: Int = 300
    ) {
        self.feedParser = feedParser
        self.contentExtractor = contentExtractor
        self.feedRepository = feedRepository
        self.aiService = aiService
        self.minWordCount = minWordCount
    }

    public func fetchAndProcessArticles() async throws -> [ProcessedArticle] {
        guard let feedRepository else {
            throw ArticleProcessingError.feedRepositoryUnavailable
        }

        let feeds = try await feedRepository.getEnabledFeeds()
        var processed: [ProcessedArticle] = []

        for feed in feeds {
            let feedArticles = try await fetchAndProcessArticles(from: feed)
            processed.append(contentsOf: feedArticles)
        }

        return processed
    }

    public func fetchAndProcessArticles(from feed: Feed) async throws -> [ProcessedArticle] {
        // Fetch raw articles from feed
        let rawArticles = try await feedParser.parseFeed(url: feed.url, feedName: feed.name)

        var seen = Set<String>()
        let distinct = rawArticles.filter { article in
            guard let identity = ArticleDeliveryIdentityBridge.identify(article.link) else {
                return false
            }
            return seen.insert(identity.articleKey).inserted
        }
        // This compatibility path has no ledger; the generator performs its
        // durable eligible-first selection before applying this cap.
        let articlesToProcess = feed.maxArticles > 0
            ? Array(distinct.prefix(feed.maxArticles))
            : distinct

        // This compatibility API cannot return per-item diagnostics, so it
        // propagates a failure. Local generation uses the structured pipeline.
        return try await withThrowingTaskGroup(of: (Int, ProcessedArticle).self) { group in
            for (index, article) in articlesToProcess.enumerated() {
                group.addTask {
                    (index, try await self.processArticle(article, mode: feed.mode))
                }
            }

            var processed: [(Int, ProcessedArticle)] = []
            for try await result in group {
                processed.append(result)
            }
            return processed.sorted { $0.0 < $1.0 }.map(\.1)
        }
    }

    public func fetchFeedArticles(feedUrl: String) async throws -> [RawArticle] {
        try await feedParser.parseFeed(url: feedUrl, feedName: "")
    }

    public func processArticle(_ article: RawArticle, mode: ProcessingMode) async throws -> ProcessedArticle {
        switch mode {
        case .fidelity:
            return try await processFidelityMode(article)
        case .briefing:
            return try await processBriefingMode(article)
        }
    }

    public func extractFullContent(url: String) async throws -> String {
        try await contentExtractor.extractContent(from: url)
    }

    public func validateFeedUrl(_ url: String) async throws -> Bool {
        try await feedParser.validateFeedURL(url)
    }

    // MARK: - Private Helpers

    private func processFidelityMode(_ article: RawArticle) async throws -> ProcessedArticle {
        // Extract full content
        let content: String
        do {
            content = try await contentExtractor.extractContent(from: article.link)
        } catch is CancellationError {
            throw CancellationError()
        } catch {
            throw ArticleProcessingError.extractionFailed
        }

        // Check word count filter
        let wordCount = contentExtractor.countWords(in: content)
        guard wordCount >= minWordCount else {
            throw ArticleProcessingError.contentTooShort
        }

        return ProcessedArticle(
            title: article.title,
            author: article.author,
            content: content,
            originalUrl: article.link,
            feedUrl: article.feedUrl,
            feedName: article.feedName,
            isSummary: false,
            publishedAt: article.publishedAt,
            wordCount: wordCount
        )
    }

    private func processBriefingMode(_ article: RawArticle) async throws -> ProcessedArticle {
        guard let aiService = aiService else {
            throw ArticleProcessingError.aiServiceUnavailable
        }

        // Extract full content first
        let fullContent: String
        do {
            fullContent = try await contentExtractor.extractContent(from: article.link)
        } catch is CancellationError {
            throw CancellationError()
        } catch {
            throw ArticleProcessingError.extractionFailed
        }

        // Generate summary
        let summary: String
        do {
            summary = try await aiService.summarize(
                title: article.title,
                content: fullContent,
                author: article.author.isEmpty ? nil : article.author
            )
        } catch is CancellationError {
            throw CancellationError()
        } catch {
            throw ArticleProcessingError.summaryFailed
        }

        let wordCount = contentExtractor.countWords(in: summary)

        return ProcessedArticle(
            title: article.title,
            author: article.author,
            content: summary,
            originalUrl: article.link,
            feedUrl: article.feedUrl,
            feedName: article.feedName,
            isSummary: true,
            publishedAt: article.publishedAt,
            wordCount: wordCount
        )
    }
}

// MARK: - Errors

public enum ArticleProcessingError: LocalizedError {
    case contentTooShort
    case aiServiceUnavailable
    case feedRepositoryUnavailable
    case extractionFailed
    case summaryFailed

    public var errorDescription: String? {
        switch self {
        case .contentTooShort:
            return "Article content does not meet minimum word count"
        case .aiServiceUnavailable:
            return "AI service is not configured for briefing mode"
        case .feedRepositoryUnavailable:
            return "Feed repository is not configured"
        case .extractionFailed:
            return "Article extraction failed"
        case .summaryFailed:
            return "Article summary failed"
        }
    }
}
