//
//  DigestRepositoryTests.swift
//  Epilogue
//
//  Created on 2026-01-26.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import Testing
import SwiftData
import Foundation
@testable import Data
@testable import Domain

@Suite("DigestRepository Tests")
struct DigestRepositoryTests {
    let container: ModelContainer
    let context: ModelContext
    let repository: DigestRepository

    init() throws {
        let schema = Schema([Feed.self, Digest.self, DigestArticle.self])
        let config = ModelConfiguration(isStoredInMemoryOnly: true)
        container = try ModelContainer(for: schema, configurations: config)
        context = ModelContext(container)
        repository = DigestRepository(modelContext: context, maxDigests: 5)
    }

    @Test("Create digest successfully")
    func testCreateDigest() async throws {
        let digest = Digest(
            epubFilePath: "/test/digest.epub",
            articleCount: 10,
            briefingCount: 5,
            deepDiveCount: 5,
            triggerType: .manual,
            isComplete: true
        )

        try await repository.createDigest(digest)

        let digests = try await repository.getAllDigests()
        #expect(digests.count == 1)
        #expect(digests.first?.articleCount == 10)
    }

    @Test("Get digest by ID")
    func testGetDigestById() async throws {
        let digest = Digest(
            epubFilePath: "/test/digest.epub",
            articleCount: 10,
            triggerType: .manual,
            isComplete: true
        )

        try await repository.createDigest(digest)

        let retrieved = try await repository.getDigest(id: digest.id)
        #expect(retrieved != nil)
        #expect(retrieved?.id == digest.id)
    }

    @Test("Get digests by date range")
    func testGetDigestsByDateRange() async throws {
        let now = Date()
        let yesterday = Calendar.current.date(byAdding: .day, value: -1, to: now)!
        let tomorrow = Calendar.current.date(byAdding: .day, value: 1, to: now)!

        let digest1 = Digest(
            generatedAt: yesterday,
            epubFilePath: "/test/digest1.epub",
            triggerType: .scheduled,
            isComplete: true
        )

        let digest2 = Digest(
            generatedAt: now,
            epubFilePath: "/test/digest2.epub",
            triggerType: .manual,
            isComplete: true
        )

        try await repository.createDigest(digest1)
        try await repository.createDigest(digest2)

        let digests = try await repository.getDigests(
            from: Calendar.current.startOfDay(for: yesterday),
            to: tomorrow
        )

        #expect(digests.count == 2)
    }

    @Test("Retention policy enforces limit")
    func testRetentionPolicyEnforcement() async throws {
        // Create 7 digests (exceeds limit of 5)
        for i in 1...7 {
            let digest = Digest(
                generatedAt: Date().addingTimeInterval(TimeInterval(i * 60)),
                epubFilePath: "/test/digest\(i).epub",
                triggerType: .manual,
                isComplete: true
            )
            try await repository.createDigest(digest)
        }

        // Should only have 5 digests (oldest 2 deleted)
        let count = try await repository.getDigestCount()
        #expect(count == 5)
    }

    @Test("Get digest count")
    func testGetDigestCount() async throws {
        #expect(try await repository.getDigestCount() == 0)

        let digest = Digest(
            epubFilePath: "/test/digest.epub",
            triggerType: .manual,
            isComplete: true
        )

        try await repository.createDigest(digest)
        #expect(try await repository.getDigestCount() == 1)
    }

    @Test("Delete digest successfully")
    func testDeleteDigest() async throws {
        let digest = Digest(
            epubFilePath: "/test/digest.epub",
            triggerType: .manual,
            isComplete: true
        )

        try await repository.createDigest(digest)
        #expect(try await repository.getDigestCount() == 1)

        try await repository.deleteDigest(id: digest.id)
        #expect(try await repository.getDigestCount() == 0)
    }

    @Test("Delete multiple digests")
    func testDeleteMultipleDigests() async throws {
        var ids: [UUID] = []

        for i in 1...3 {
            let digest = Digest(
                epubFilePath: "/test/digest\(i).epub",
                triggerType: .manual,
                isComplete: true
            )
            try await repository.createDigest(digest)
            ids.append(digest.id)
        }

        #expect(try await repository.getDigestCount() == 3)

        try await repository.deleteDigests(ids: Array(ids.prefix(2)))
        #expect(try await repository.getDigestCount() == 1)
    }

    @Test("Update digest properties")
    func testUpdateDigest() async throws {
        let digest = Digest(
            epubFilePath: "/test/digest.epub",
            articleCount: 5,
            triggerType: .manual,
            isComplete: false
        )

        try await repository.createDigest(digest)

        digest.isComplete = true
        digest.articleCount = 10
        digest.errorMessage = nil

        try await repository.updateDigest(digest)

        let updated = try await repository.getDigest(id: digest.id)
        #expect(updated?.isComplete == true)
        #expect(updated?.articleCount == 10)
    }
}
