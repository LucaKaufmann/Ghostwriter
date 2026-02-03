//
//  ArticleRepositoryTests.swift
//  Epilogue
//
//  Created on 2026-02-03.
//

import Testing
import Foundation
@testable import Data
@testable import Domain

@Suite("ArticleRepository Tests")
struct ArticleRepositoryTests {
    @Test("Fidelity mode throws when content is too short")
    func testFidelityContentTooShort() async {
        let feedParser = StubFeedParser(articles: [])
        let contentExtractor = StubContentExtractor(content: "short", wordCount: 3, minimum: 5)
        let repository = ArticleRepository(
            feedParser: feedParser,
            contentExtractor: contentExtractor,
            aiService: nil,
            minWordCount: 5
        )

        let article = RawArticle(
            title: "Title",
            link: "https://example.com/article",
            author: "",
            feedUrl: "https://example.com/feed",
            feedName: "Feed"
        )

        await #expect(throws: ArticleProcessingError.contentTooShort) {
            _ = try await repository.processArticle(article, mode: .fidelity)
        }
    }

    @Test("Briefing mode throws when AI service is missing")
    func testBriefingModeRequiresAI() async {
        let feedParser = StubFeedParser(articles: [])
        let contentExtractor = StubContentExtractor(content: "full", wordCount: 10, minimum: 0)
        let repository = ArticleRepository(
            feedParser: feedParser,
            contentExtractor: contentExtractor,
            aiService: nil
        )

        let article = RawArticle(
            title: "Title",
            link: "https://example.com/article",
            author: "",
            feedUrl: "https://example.com/feed",
            feedName: "Feed"
        )

        await #expect(throws: ArticleProcessingError.aiServiceUnavailable) {
            _ = try await repository.processArticle(article, mode: .briefing)
        }
    }

    @Test("Briefing mode returns summarized article")
    func testBriefingModeReturnsSummary() async throws {
        let feedParser = StubFeedParser(articles: [])
        let contentExtractor = StubContentExtractor(content: "full", wordCount: 8, minimum: 0)
        let aiService = StubAIService(summary: "Summary content")
        let repository = ArticleRepository(
            feedParser: feedParser,
            contentExtractor: contentExtractor,
            aiService: aiService,
            minWordCount: 0
        )

        let article = RawArticle(
            title: "Title",
            link: "https://example.com/article",
            author: "Jane",
            feedUrl: "https://example.com/feed",
            feedName: "Feed"
        )

        let processed = try await repository.processArticle(article, mode: .briefing)

        #expect(processed.isSummary == true)
        #expect(processed.content == "Summary content")
        #expect(processed.wordCount == 8)
        #expect(processed.feedName == "Feed")
    }

    @Test("Fetch and process respects max articles")
    func testFetchRespectsMaxArticles() async throws {
        let articles = [
            RawArticle(
                title: "A",
                link: "https://example.com/a",
                author: "",
                feedUrl: "https://example.com/feed",
                feedName: "Feed"
            ),
            RawArticle(
                title: "B",
                link: "https://example.com/b",
                author: "",
                feedUrl: "https://example.com/feed",
                feedName: "Feed"
            )
        ]

        let feedParser = StubFeedParser(articles: articles)
        let contentExtractor = StubContentExtractor(content: "content", wordCount: 5, minimum: 0)
        let repository = ArticleRepository(
            feedParser: feedParser,
            contentExtractor: contentExtractor,
            aiService: nil,
            minWordCount: 0
        )

        let feed = Feed(
            url: "https://example.com/feed",
            name: "Feed",
            mode: .fidelity,
            maxArticles: 1
        )

        let processed = try await repository.fetchAndProcessArticles(from: feed)

        #expect(processed.count == 1)
        #expect(processed.first?.title == "A")
    }
}

private struct StubFeedParser: FeedParserProtocol {
    let articles: [RawArticle]
    let validateResult: Bool

    init(articles: [RawArticle], validateResult: Bool = true) {
        self.articles = articles
        self.validateResult = validateResult
    }

    func parseFeed(url: String, feedName: String) async throws -> [RawArticle] {
        articles
    }

    func validateFeedURL(_ url: String) async throws -> Bool {
        validateResult
    }
}

private struct StubContentExtractor: ContentExtractorProtocol {
    let content: String
    let wordCount: Int
    let minimum: Int

    func extractContent(from url: String) async throws -> String {
        content
    }

    func countWords(in html: String) -> Int {
        wordCount
    }

    func meetsMinimumWordCount(_ html: String) -> Bool {
        wordCount >= minimum
    }
}

private struct StubAIService: AIServiceProtocol {
    let summary: String
    var provider: AIProvider { .openAI }

    func summarize(title: String, content: String, author: String?) async throws -> String {
        summary
    }

    func validateConfiguration() async throws -> Bool {
        true
    }
}
