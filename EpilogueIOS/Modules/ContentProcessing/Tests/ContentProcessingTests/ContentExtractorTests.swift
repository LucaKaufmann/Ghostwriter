//
//  ContentExtractorTests.swift
//  Epilogue
//
//  Created on 2026-01-26.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import Testing
import Foundation
@testable import ContentProcessing

@Suite("ContentExtractor Tests")
struct ContentExtractorTests {
    @Test("ContentExtractor initializes correctly")
    func testInitialization() {
        _ = ContentExtractor()
        #expect(true)
    }

    @Test("Count words in HTML")
    func testWordCount() {
        let extractor = ContentExtractor()
        let html = "<p>This is a test with five words.</p>"
        let count = extractor.countWords(in: html)
        #expect(count == 7)
    }

    @Test("Check minimum word count")
    func testMinimumWordCount() {
        let extractor = ContentExtractor(minWordCount: 5)
        let shortHTML = "<p>Too short</p>"
        let longHTML = "<p>This is a longer piece of content with enough words.</p>"

        #expect(extractor.meetsMinimumWordCount(shortHTML) == false)
        #expect(extractor.meetsMinimumWordCount(longHTML) == true)
    }

    @Test("Invalid URL throws error")
    func testInvalidURL() async throws {
        let extractor = ContentExtractor()
        do {
            _ = try await extractor.extractContent(from: "not a url")
            #expect(Bool(false), "Expected invalid URL error")
        } catch {
            #expect(true)
        }
    }
}
