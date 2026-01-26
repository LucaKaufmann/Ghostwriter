//
//  FeedParserTests.swift
//  Epilogue
//
//  Created on 2026-01-26.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import Testing
import Foundation
@testable import ContentProcessing

@Suite("FeedParser Tests")
struct FeedParserTests {
    @Test("FeedParser initializes correctly")
    func testInitialization() {
        let parser = FeedParser()
        #expect(parser != nil)
    }

    @Test("Invalid URL throws error")
    func testInvalidURL() async throws {
        let parser = FeedParser()
        await #expect(throws: FeedParserError.invalidURL) {
            _ = try await parser.parseFeed(url: "not a url", feedName: "Test")
        }
    }
}
