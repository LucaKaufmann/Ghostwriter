//
//  ArticleRepositoryTests.swift
//  Epilogue
//

import Testing
import Foundation
@testable import Data
@testable import Domain

@Suite("ArticleRepository Tests")
struct ArticleRepositoryTests {
    @Test("Fetch and process articles uses enabled feeds")
    func testFetchAndProcessArticlesUsesEnabledFeeds() async throws {
        let enabledFeed = Feed(
            url: "https://example.com/enabled.xml",
            name: "Enabled Feed",
            mode: .fidelity,
            maxArticles: 1,
            isEnabled: true
        )
        let disabledFeed = Feed(
            url: "https://example.com/disabled.xml",
            name: "Disabled Feed",
            mode: .fidelity,
            isEnabled: false
        )

        let repository = ArticleRepository(
            feedParser: FakeFeedParser(
                articlesByURL: [
                    enabledFeed.url: [
                        RawArticle(
                            title: "Enabled Article 1",
                            link: "https://example.com/enabled-1",
                            author: "Author",
                            feedUrl: enabledFeed.url,
                            feedName: enabledFeed.name
                        ),
                        RawArticle(
                            title: "Enabled Article 2",
                            link: "https://example.com/enabled-2",
                            author: "Author",
                            feedUrl: enabledFeed.url,
                            feedName: enabledFeed.name
                        )
                    ],
                    disabledFeed.url: [
                        RawArticle(
                            title: "Disabled Article",
                            link: "https://example.com/disabled-1",
                            feedUrl: disabledFeed.url,
                            feedName: disabledFeed.name
                        )
                    ]
                ]
            ),
            contentExtractor: FakeContentExtractor(
                contentByURL: [
                    "https://example.com/enabled-1": "one two three",
                    "https://example.com/enabled-2": "four five six",
                    "https://example.com/disabled-1": "seven eight nine"
                ]
            ),
            feedRepository: FakeFeedRepository(feeds: [enabledFeed, disabledFeed]),
            minWordCount: 0
        )

        let articles = try await repository.fetchAndProcessArticles()

        #expect(articles.map(\.title) == ["Enabled Article 1"])
        #expect(articles.first?.feedUrl == enabledFeed.url)
        #expect(articles.first?.wordCount == 3)
    }

    @Test("Fetch and process articles without feed repository throws")
    func testFetchAndProcessArticlesWithoutFeedRepositoryThrows() async {
        let repository = ArticleRepository(
            feedParser: FakeFeedParser(articlesByURL: [:]),
            contentExtractor: FakeContentExtractor(contentByURL: [:]),
            minWordCount: 0
        )

        await #expect(throws: ArticleProcessingError.feedRepositoryUnavailable) {
            try await repository.fetchAndProcessArticles()
        }
    }
}

private final class FakeFeedRepository: FeedRepositoryProtocol, @unchecked Sendable {
    private let feeds: [Feed]

    init(feeds: [Feed]) {
        self.feeds = feeds
    }

    func getAllFeeds() async throws -> [Feed] { feeds }

    func getEnabledFeeds() async throws -> [Feed] {
        feeds.filter(\.isEnabled)
    }

    func getFeed(url: String) async throws -> Feed? {
        feeds.first { $0.url == url }
    }

    func addFeed(_ feed: Feed) async throws {}

    func updateFeed(_ feed: Feed) async throws {}

    func deleteFeed(url: String) async throws {}

    func updateLastFetched(url: String, timestamp: Int64) async throws {}

    func feedExists(url: String) async throws -> Bool {
        feeds.contains { $0.url == url }
    }

    func upsertAll(_ feeds: [Feed]) async throws {}

    func deleteByURLs(_ urls: [String]) async throws {}

    func clearAllLocallyModified() async throws {}

    func getLocallyModifiedFeeds() async throws -> [Feed] { [] }

    func markAsLocallyModified(url: String) async throws {}
}

private struct FakeFeedParser: FeedParserProtocol {
    let articlesByURL: [String: [RawArticle]]

    func parseFeed(url: String, feedName: String) async throws -> [RawArticle] {
        articlesByURL[url] ?? []
    }

    func validateFeedURL(_ url: String) async throws -> Bool {
        articlesByURL[url] != nil
    }
}

private struct FakeContentExtractor: ContentExtractorProtocol {
    let contentByURL: [String: String]

    func extractContent(from url: String) async throws -> String {
        contentByURL[url] ?? ""
    }

    func countWords(in html: String) -> Int {
        html.split(whereSeparator: \.isWhitespace).count
    }

    func meetsMinimumWordCount(_ html: String) -> Bool {
        countWords(in: html) > 0
    }
}
