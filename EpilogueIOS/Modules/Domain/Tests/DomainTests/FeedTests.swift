//
//  FeedTests.swift
//  Epilogue
//
//  Created on 2026-01-26.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import Testing
@testable import Domain

@Suite("Feed Model Tests")
struct FeedTests {
    @Test("Feed initialization with all parameters")
    func testFeedInitialization() {
        let feed = Feed(
            url: "https://example.com/feed.xml",
            name: "Example Feed",
            mode: .fidelity,
            lastFetched: 1234567890,
            maxArticles: 10,
            isEnabled: true
        )

        #expect(feed.url == "https://example.com/feed.xml")
        #expect(feed.name == "Example Feed")
        #expect(feed.mode == .fidelity)
        #expect(feed.lastFetched == 1234567890)
        #expect(feed.maxArticles == 10)
        #expect(feed.isEnabled == true)
    }

    @Test("Feed initialization with default values")
    func testFeedDefaultValues() {
        let feed = Feed(
            url: "https://example.com/feed.xml",
            name: "Example Feed",
            mode: .briefing
        )

        #expect(feed.lastFetched == 0)
        #expect(feed.maxArticles == 0)
        #expect(feed.isEnabled == true)
    }

    @Test("ProcessingMode enum values")
    func testProcessingModeEnum() {
        #expect(ProcessingMode.fidelity.displayName == "Deep Dive")
        #expect(ProcessingMode.briefing.displayName == "Briefing")
    }

    @Test("ProcessingMode raw values")
    func testProcessingModeRawValues() {
        #expect(ProcessingMode.fidelity.rawValue == "FIDELITY")
        #expect(ProcessingMode.briefing.rawValue == "BRIEFING")
    }
}

@Suite("ProcessedArticle Tests")
struct ProcessedArticleTests {
    @Test("ProcessedArticle initialization")
    func testProcessedArticleInit() {
        let article = ProcessedArticle(
            title: "Test Article",
            author: "John Doe",
            content: "<p>Test content</p>",
            originalUrl: "https://example.com/article",
            feedUrl: "https://example.com/feed.xml",
            feedName: "Example Feed",
            isSummary: false,
            wordCount: 100
        )

        #expect(article.title == "Test Article")
        #expect(article.author == "John Doe")
        #expect(article.isSummary == false)
        #expect(article.wordCount == 100)
    }

    @Test("ProcessedArticle to DigestArticle conversion")
    func testConversionToDigestArticle() {
        let processedArticle = ProcessedArticle(
            title: "Test Article",
            author: "Jane Doe",
            content: "<p>Content</p>",
            originalUrl: "https://example.com/article",
            feedUrl: "https://example.com/feed.xml",
            feedName: "Example Feed",
            isSummary: true,
            wordCount: 50
        )

        let digestArticle = processedArticle.toDigestArticle(
            contentType: .briefing,
            orderIndex: 0
        )

        #expect(digestArticle.title == "Test Article")
        #expect(digestArticle.author == "Jane Doe")
        #expect(digestArticle.contentType == .briefing)
        #expect(digestArticle.orderIndex == 0)
        #expect(digestArticle.wordCount == 50)
    }
}

@Suite("ContentType Tests")
struct ContentTypeTests {
    @Test("ContentType display names")
    func testContentTypeDisplayNames() {
        #expect(ContentType.briefing.displayName == "Briefing")
        #expect(ContentType.deepDive.displayName == "Deep Dive")
    }

    @Test("ContentType section names")
    func testContentTypeSectionNames() {
        #expect(ContentType.briefing.sectionName == "Briefings")
        #expect(ContentType.deepDive.sectionName == "Deep Dives")
    }

    @Test("ContentType sort order")
    func testContentTypeSortOrder() {
        #expect(ContentType.briefing.sortOrder < ContentType.deepDive.sortOrder)
        #expect(ContentType.briefing.sortOrder == 0)
        #expect(ContentType.deepDive.sortOrder == 1)
    }
}
