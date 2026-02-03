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
        _ = EpilogueFeedParser()
        #expect(true)
    }

    @Test("Invalid URL throws error")
    func testInvalidURL() async throws {
        let parser = EpilogueFeedParser()
        do {
            _ = try await parser.validateFeedURL("")
            #expect(Bool(false), "Expected invalid URL error")
        } catch {
            #expect(true)
        }
    }
}
