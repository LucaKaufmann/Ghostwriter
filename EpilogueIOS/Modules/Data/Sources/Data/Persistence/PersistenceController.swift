//
//  PersistenceController.swift
//  Epilogue
//
//  Created on 2026-01-26.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import Foundation
import SwiftData
import Domain

/// Manages the SwiftData model container and provides access to the model context.
@MainActor
public final class PersistenceController {
    /// Shared singleton instance for production use
    public static let shared = PersistenceController()

    /// In-memory instance for testing and previews
    public static let preview: PersistenceController = {
        let controller = PersistenceController(inMemory: true)

        // Add sample data for previews
        let context = controller.container.mainContext

        let sampleFeed1 = Feed(
            url: "https://example.com/feed1.xml",
            name: "Tech News",
            mode: .briefing,
            maxArticles: 10
        )

        let sampleFeed2 = Feed(
            url: "https://example.com/feed2.xml",
            name: "Deep Reads",
            mode: .fidelity,
            maxArticles: 5
        )

        context.insert(sampleFeed1)
        context.insert(sampleFeed2)

        let sampleDigest = Digest(
            epubFilePath: "/Documents/Epilogue/Epilogue_2026-01-26.epub",
            articleCount: 15,
            briefingCount: 10,
            deepDiveCount: 5,
            triggerType: .manual,
            fileSizeBytes: 1024000,
            isComplete: true
        )

        context.insert(sampleDigest)

        try? context.save()

        return controller
    }()

    /// The SwiftData model container
    public let container: ModelContainer

    /// Initialize the persistence controller
    /// - Parameter inMemory: If true, uses an in-memory store for testing
    private init(inMemory: Bool = false) {
        let schema = Schema([
            Feed.self,
            Digest.self,
            DigestArticle.self
        ])

        let modelConfiguration: ModelConfiguration
        if inMemory {
            modelConfiguration = ModelConfiguration(
                schema: schema,
                isStoredInMemoryOnly: true
            )
        } else {
            modelConfiguration = ModelConfiguration(
                schema: schema,
                isStoredInMemoryOnly: false
            )
        }

        do {
            container = try ModelContainer(
                for: schema,
                configurations: [modelConfiguration]
            )
        } catch {
            fatalError("Failed to create ModelContainer: \(error)")
        }
    }

    /// Creates a new background context for async operations
    public func newBackgroundContext() -> ModelContext {
        return ModelContext(container)
    }
}
