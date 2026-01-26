//
//  EPUBBuilderTests.swift
//  Epilogue
//
//  Created on 2026-01-26.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import Testing
import Foundation
@testable import EPUBGeneration
@testable import Domain

@Suite("EPUBBuilder Tests")
struct EPUBBuilderTests {
    @Test("EPUBBuilder initializes correctly")
    func testInitialization() {
        let builder = EPUBBuilder()
        #expect(builder != nil)
    }

    @Test("Generate EPUB with sample articles")
    func testGenerateEPUB() throws {
        let builder = EPUBBuilder()

        let articles = [
            ProcessedArticle(
                title: "Test Article 1",
                author: "John Doe",
                content: "<p>This is a test briefing.</p>",
                originalUrl: "https://example.com/1",
                feedUrl: "https://example.com/feed",
                feedName: "Test Feed",
                isSummary: true,
                wordCount: 5
            ),
            ProcessedArticle(
                title: "Test Article 2",
                author: "Jane Smith",
                content: "<p>This is a test deep dive article.</p>",
                originalUrl: "https://example.com/2",
                feedUrl: "https://example.com/feed",
                feedName: "Test Feed",
                isSummary: false,
                wordCount: 7
            )
        ]

        let tempDir = FileManager.default.temporaryDirectory
        let outputPath = tempDir.appendingPathComponent("test.epub").path

        let result = try builder.generateEPUB(
            articles: articles,
            outputPath: outputPath
        )

        #expect(FileManager.default.fileExists(atPath: result.path))

        // Cleanup
        try? FileManager.default.removeItem(at: result)
    }

    @Test("EPUB stylesheet is not empty")
    func testStylesheet() {
        let css = EPUBStylesheet.einkOptimizedCSS
        #expect(!css.isEmpty)
        #expect(css.contains("body"))
        #expect(css.contains("e-ink"))
    }
}
