//
//  ContentExtractor.swift
//  Epilogue
//
//  Created on 2026-01-26.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import Foundation
import SwiftSoup

/// Service for extracting and cleaning article content from HTML
public final class ContentExtractor: Sendable {
    private let session: URLSession
    private let minWordCount: Int

    public init(session: URLSession = .shared, minWordCount: Int = 300) {
        self.session = session
        self.minWordCount = minWordCount
    }

    /// Extract full article content from a URL
    public func extractContent(from url: String) async throws -> String {
        guard let articleURL = URL(string: url) else {
            throw ContentExtractorError.invalidURL
        }

        // Fetch HTML
        let (data, response) = try await session.data(from: articleURL)

        guard let httpResponse = response as? HTTPURLResponse,
              (200...299).contains(httpResponse.statusCode) else {
            throw ContentExtractorError.networkError
        }

        guard let html = String(data: data, encoding: .utf8) else {
            throw ContentExtractorError.invalidEncoding
        }

        // Parse and extract content
        return try extractArticleContent(from: html)
    }

    /// Count words in HTML content
    public func countWords(in html: String) -> Int {
        do {
            let doc = try SwiftSoup.parse(html)
            let text = try doc.text()
            let words = text.components(separatedBy: .whitespacesAndNewlines)
            return words.filter { !$0.isEmpty }.count
        } catch {
            return 0
        }
    }

    /// Check if content meets minimum word count
    public func meetsMinimumWordCount(_ html: String) -> Bool {
        countWords(in: html) >= minWordCount
    }

    // MARK: - Private Helpers

    private func extractArticleContent(from html: String) throws -> String {
        let doc = try SwiftSoup.parse(html)

        // Remove unwanted elements
        try removeUnwantedElements(from: doc)

        // Try to find main content
        let content = try findMainContent(in: doc)

        // Clean and format
        let cleaned = try cleanContent(content)

        return cleaned
    }

    private func removeUnwantedElements(from doc: Document) throws {
        // Remove scripts, styles, ads, navigation, etc.
        let unwantedSelectors = [
            "script", "style", "nav", "header", "footer",
            "aside", "iframe", "noscript",
            ".advertisement", ".ad", ".ads", ".social-share",
            ".comments", ".related-posts", "#comments"
        ]

        for selector in unwantedSelectors {
            try doc.select(selector).remove()
        }
    }

    private func findMainContent(in doc: Document) throws -> Element {
        // Try common article selectors
        let contentSelectors = [
            "article",
            "[role='main']",
            "main",
            ".post-content",
            ".article-content",
            ".entry-content",
            "#content",
            ".content"
        ]

        for selector in contentSelectors {
            let elements = try doc.select(selector)
            if let element = elements.first(), !element.text().isEmpty {
                return element
            }
        }

        // Fall back to body
        if let body = doc.body() {
            return body
        }

        throw ContentExtractorError.noContentFound
    }

    private func cleanContent(_ element: Element) throws -> String {
        // Get HTML
        var html = try element.html()

        // Remove excessive whitespace
        html = html.replacingOccurrences(
            of: "\\s+",
            with: " ",
            options: .regularExpression
        )

        // Remove empty paragraphs
        html = html.replacingOccurrences(
            of: "<p>\\s*</p>",
            with: "",
            options: .regularExpression
        )

        // Trim
        html = html.trimmingCharacters(in: .whitespacesAndNewlines)

        return html
    }
}

// MARK: - Errors

public enum ContentExtractorError: LocalizedError {
    case invalidURL
    case networkError
    case invalidEncoding
    case noContentFound
    case contentTooShort

    public var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "Invalid article URL"
        case .networkError:
            return "Network error while fetching article"
        case .invalidEncoding:
            return "Invalid content encoding"
        case .noContentFound:
            return "No article content found"
        case .contentTooShort:
            return "Article content is too short"
        }
    }
}
