//
//  ContentProcessingProtocols.swift
//  Domain
//

import Foundation

public protocol FeedParserProtocol: Sendable {
    func parseFeed(url: String, feedName: String) async throws -> [RawArticle]
    func validateFeedURL(_ url: String) async throws -> Bool
}

public protocol ContentExtractorProtocol: Sendable {
    func extractContent(from url: String) async throws -> String
    func countWords(in html: String) -> Int
    func meetsMinimumWordCount(_ html: String) -> Bool
}
