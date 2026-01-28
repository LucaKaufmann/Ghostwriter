//
//  FeedParser.swift
//  Epilogue
//
//  Created on 2026-01-26.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import Foundation
import FeedKit
import Domain

/// Service for parsing RSS and Atom feeds
public final class EpilogueFeedParser: Sendable {
    private let session: URLSession

    public init(session: URLSession = .shared) {
        self.session = session
    }

    /// Parse a feed from a URL and return raw articles
    public func parseFeed(url: String, feedName: String) async throws -> [RawArticle] {
        guard let feedURL = URL(string: url) else {
            throw FeedParserError.invalidURL
        }

        // Fetch feed data
        let (data, response) = try await session.data(from: feedURL)

        guard let httpResponse = response as? HTTPURLResponse,
              (200...299).contains(httpResponse.statusCode) else {
            throw FeedParserError.networkError
        }

        // Parse feed
        let parser = FeedKit.FeedParser(data: data)
        let result = parser.parse()

        switch result {
        case .success(let feed):
            return try extractArticles(from: feed, feedUrl: url, feedName: feedName)
        case .failure(let error):
            throw FeedParserError.parsingFailed(error.localizedDescription)
        }
    }

    /// Validate that a feed URL is accessible and parseable
    public func validateFeedURL(_ url: String) async throws -> Bool {
        guard let feedURL = URL(string: url) else {
            throw FeedParserError.invalidURL
        }

        let (data, response) = try await session.data(from: feedURL)

        guard let httpResponse = response as? HTTPURLResponse,
              (200...299).contains(httpResponse.statusCode) else {
            return false
        }

        let parser = FeedKit.FeedParser(data: data)
        let result = parser.parse()

        switch result {
        case .success:
            return true
        case .failure:
            return false
        }
    }

    // MARK: - Private Helpers

    private func extractArticles(
        from feed: FeedKit.Feed,
        feedUrl: String,
        feedName: String
    ) throws -> [RawArticle] {
        var articles: [RawArticle] = []

        switch feed {
        case .atom(let atomFeed):
            articles = extractFromAtom(atomFeed, feedUrl: feedUrl, feedName: feedName)
        case .rss(let rssFeed):
            articles = extractFromRSS(rssFeed, feedUrl: feedUrl, feedName: feedName)
        case .json(let jsonFeed):
            articles = extractFromJSON(jsonFeed, feedUrl: feedUrl, feedName: feedName)
        }

        return articles
    }

    private func extractFromRSS(
        _ feed: RSSFeed,
        feedUrl: String,
        feedName: String
    ) -> [RawArticle] {
        guard let items = feed.items else { return [] }

        return items.compactMap { item in
            guard let title = item.title,
                  let link = item.link else {
                return nil
            }

            return RawArticle(
                title: title,
                link: link,
                author: item.author ?? item.dublinCore?.dcCreator ?? "",
                publishedAt: item.pubDate,
                feedUrl: feedUrl,
                feedName: feedName
            )
        }
    }

    private func extractFromAtom(
        _ feed: AtomFeed,
        feedUrl: String,
        feedName: String
    ) -> [RawArticle] {
        guard let entries = feed.entries else { return [] }

        return entries.compactMap { entry in
            guard let title = entry.title,
                  let link = entry.links?.first?.attributes?.href else {
                return nil
            }

            let author = entry.authors?.first?.name ?? ""
            let publishedAt = entry.published ?? entry.updated

            return RawArticle(
                title: title,
                link: link,
                author: author,
                publishedAt: publishedAt,
                feedUrl: feedUrl,
                feedName: feedName
            )
        }
    }

    private func extractFromJSON(
        _ feed: JSONFeed,
        feedUrl: String,
        feedName: String
    ) -> [RawArticle] {
        guard let items = feed.items else { return [] }

        return items.compactMap { item -> RawArticle? in
            guard let title = item.title,
                  let url = item.url else {
                return nil
            }

            let author = item.author?.name ?? ""
            let publishedAt = item.datePublished

            return RawArticle(
                title: title,
                link: url,
                author: author,
                publishedAt: publishedAt,
                feedUrl: feedUrl,
                feedName: feedName
            )
        }
    }
}

// MARK: - Errors

public enum FeedParserError: LocalizedError {
    case invalidURL
    case networkError
    case parsingFailed(String)

    public var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "Invalid feed URL"
        case .networkError:
            return "Network error while fetching feed"
        case .parsingFailed(let message):
            return "Failed to parse feed: \(message)"
        }
    }
}
