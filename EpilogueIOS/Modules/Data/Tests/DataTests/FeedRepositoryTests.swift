//
//  FeedRepositoryTests.swift
//  Epilogue
//
//  Created on 2026-01-26.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import Testing
import SwiftData
@testable import Data
@testable import Domain

@Suite("FeedRepository Tests")
struct FeedRepositoryTests {
    let container: ModelContainer
    let context: ModelContext
    let repository: FeedRepository

    init() throws {
        let schema = Schema([Feed.self, Digest.self, DigestArticle.self])
        let config = ModelConfiguration(isStoredInMemoryOnly: true)
        container = try ModelContainer(for: schema, configurations: config)
        context = ModelContext(container)
        repository = FeedRepository(modelContext: context)
    }

    @Test("Add feed successfully")
    func testAddFeed() async throws {
        let feed = Feed(
            url: "https://example.com/feed.xml",
            name: "Test Feed",
            mode: .briefing
        )

        try await repository.addFeed(feed)

        let feeds = try await repository.getAllFeeds()
        #expect(feeds.count == 1)
        #expect(feeds.first?.url == "https://example.com/feed.xml")
        #expect(feeds.first?.name == "Test Feed")
    }

    @Test("Add duplicate feed throws error")
    func testAddDuplicateFeed() async throws {
        let feed1 = Feed(
            url: "https://example.com/feed.xml",
            name: "Feed 1",
            mode: .briefing
        )

        try await repository.addFeed(feed1)

        let feed2 = Feed(
            url: "https://example.com/feed.xml",
            name: "Feed 2",
            mode: .fidelity
        )

        await #expect(throws: FeedRepositoryError.feedAlreadyExists) {
            try await repository.addFeed(feed2)
        }
    }

    @Test("Get enabled feeds only")
    func testGetEnabledFeeds() async throws {
        let feed1 = Feed(
            url: "https://example.com/feed1.xml",
            name: "Enabled Feed",
            mode: .briefing,
            isEnabled: true
        )

        let feed2 = Feed(
            url: "https://example.com/feed2.xml",
            name: "Disabled Feed",
            mode: .fidelity,
            isEnabled: false
        )

        try await repository.addFeed(feed1)
        try await repository.addFeed(feed2)

        let enabledFeeds = try await repository.getEnabledFeeds()
        #expect(enabledFeeds.count == 1)
        #expect(enabledFeeds.first?.url == "https://example.com/feed1.xml")
    }

    @Test("Update last fetched timestamp")
    func testUpdateLastFetched() async throws {
        let feed = Feed(
            url: "https://example.com/feed.xml",
            name: "Test Feed",
            mode: .briefing
        )

        try await repository.addFeed(feed)

        let timestamp: Int64 = 1234567890
        try await repository.updateLastFetched(url: feed.url, timestamp: timestamp)

        let updatedFeed = try await repository.getFeed(url: feed.url)
        #expect(updatedFeed?.lastFetched == timestamp)
    }

    @Test("Delete feed successfully")
    func testDeleteFeed() async throws {
        let feed = Feed(
            url: "https://example.com/feed.xml",
            name: "Test Feed",
            mode: .briefing
        )

        try await repository.addFeed(feed)
        #expect(try await repository.feedExists(url: feed.url))

        try await repository.deleteFeed(url: feed.url)
        #expect(try await repository.feedExists(url: feed.url) == false)
    }

    @Test("Delete non-existent feed throws error")
    func testDeleteNonExistentFeed() async throws {
        await #expect(throws: FeedRepositoryError.feedNotFound) {
            try await repository.deleteFeed(url: "https://nonexistent.com/feed.xml")
        }
    }

    @Test("Update feed properties")
    func testUpdateFeed() async throws {
        let feed = Feed(
            url: "https://example.com/feed.xml",
            name: "Original Name",
            mode: .briefing
        )

        try await repository.addFeed(feed)

        // Modify feed properties
        feed.name = "Updated Name"
        feed.mode = .fidelity
        feed.maxArticles = 10

        try await repository.updateFeed(feed)

        let updatedFeed = try await repository.getFeed(url: feed.url)
        #expect(updatedFeed?.name == "Updated Name")
        #expect(updatedFeed?.mode == .fidelity)
        #expect(updatedFeed?.maxArticles == 10)
    }
}
