//
//  ScreenshotDataSeeder.swift
//  Epilogue
//
//  Seeds deterministic, realistic mock content used by App Store screenshots.
//

import Foundation
import SwiftData
import Domain

@MainActor
enum ScreenshotDataSeeder {
    static func seedIfNeeded(context: ModelContext, options: ScreenshotLaunchOptions) {
        guard options.isEnabled else { return }

        do {
            let fixture = try loadFixture(options: options)
            if options.resetData {
                try clearExistingData(context: context)
            }
            try seed(fixture: fixture, context: context)
        } catch {
            print("[ScreenshotDataSeeder] Failed to seed screenshot data: \(error)")
        }
    }

    private static func clearExistingData(context: ModelContext) throws {
        let digests = try context.fetch(FetchDescriptor<Digest>())
        for digest in digests {
            context.delete(digest)
        }

        let feeds = try context.fetch(FetchDescriptor<Feed>())
        for feed in feeds {
            context.delete(feed)
        }

        try context.save()
    }

    private static func seed(fixture: ScreenshotFixture, context: ModelContext) throws {
        let documentsDirectory = try screenshotDocumentsDirectory()

        for feed in fixture.feeds {
            let model = Feed(
                url: feed.url,
                name: feed.name,
                mode: feed.mode,
                lastFetched: feed.lastFetched,
                maxArticles: feed.maxArticles,
                isEnabled: feed.isEnabled,
                createdAt: feed.createdAt
            )
            context.insert(model)
        }

        for digest in fixture.digests {
            let digestFileURL = documentsDirectory.appendingPathComponent(digest.epubFileName)
            if !FileManager.default.fileExists(atPath: digestFileURL.path) {
                try "Mock EPUB for screenshot automation".data(using: .utf8)?.write(to: digestFileURL)
            }

            let digestModel = Digest(
                generatedAt: digest.generatedAt,
                epubFilePath: digestFileURL.path,
                articleCount: digest.articleCount,
                briefingCount: digest.briefingCount,
                deepDiveCount: digest.deepDiveCount,
                triggerType: digest.triggerType,
                fileSizeBytes: digest.fileSizeBytes,
                isComplete: true,
                errorMessage: nil,
                remoteId: digest.remoteId,
                period: digest.period,
                articles: []
            )

            context.insert(digestModel)

            for (index, article) in digest.articles.enumerated() {
                let articleModel = DigestArticle(
                    digest: digestModel,
                    title: article.title,
                    author: article.author,
                    content: article.content,
                    originalUrl: article.originalUrl,
                    feedUrl: article.feedUrl,
                    feedName: article.feedName,
                    contentType: article.contentType,
                    publishedAt: article.publishedAt,
                    orderIndex: article.orderIndex ?? index,
                    wordCount: article.wordCount
                )
                context.insert(articleModel)
                digestModel.articles.append(articleModel)
            }
        }

        try context.save()
    }

    private static func screenshotDocumentsDirectory() throws -> URL {
        guard let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first else {
            throw NSError(domain: "ScreenshotDataSeeder", code: 1, userInfo: [NSLocalizedDescriptionKey: "Could not resolve documents directory"]) }

        let directory = documents.appendingPathComponent("Screenshots", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        return directory
    }

    private static func loadFixture(options: ScreenshotLaunchOptions) throws -> ScreenshotFixture {
        if let fixturePath = options.fixturePath, !fixturePath.isEmpty {
            let externalURL = URL(fileURLWithPath: fixturePath)
            let data = try Data(contentsOf: externalURL)
            return try JSONDecoder.screenshotFixtureDecoder.decode(ScreenshotFixture.self, from: data)
        }

        let bundledURL = Bundle.main.url(forResource: "default", withExtension: "json", subdirectory: "ScreenshotFixtures")
            ?? Bundle.main.url(forResource: "default", withExtension: "json")

        guard let bundledURL else {
            throw NSError(domain: "ScreenshotDataSeeder", code: 2, userInfo: [NSLocalizedDescriptionKey: "Missing default screenshot fixture"])
        }

        let data = try Data(contentsOf: bundledURL)
        return try JSONDecoder.screenshotFixtureDecoder.decode(ScreenshotFixture.self, from: data)
    }
}

private struct ScreenshotFixture: Decodable {
    let feeds: [FeedFixture]
    let digests: [DigestFixture]
}

private struct FeedFixture: Decodable {
    let url: String
    let name: String
    let mode: ProcessingMode
    let maxArticles: Int
    let isEnabled: Bool
    let lastFetched: Int64
    let createdAt: Date
}

private struct DigestFixture: Decodable {
    let generatedAt: Date
    let epubFileName: String
    let articleCount: Int
    let briefingCount: Int
    let deepDiveCount: Int
    let triggerType: TriggerType
    let fileSizeBytes: Int64
    let remoteId: String?
    let period: String?
    let articles: [DigestArticleFixture]
}

private struct DigestArticleFixture: Decodable {
    let title: String
    let author: String
    let content: String
    let originalUrl: String
    let feedUrl: String
    let feedName: String
    let contentType: ContentType
    let publishedAt: Date?
    let orderIndex: Int?
    let wordCount: Int
}

private extension JSONDecoder {
    static var screenshotFixtureDecoder: JSONDecoder {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return decoder
    }
}
