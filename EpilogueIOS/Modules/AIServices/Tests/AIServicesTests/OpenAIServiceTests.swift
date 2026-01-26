//
//  OpenAIServiceTests.swift
//  Epilogue
//
//  Created on 2026-01-26.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import Testing
import Foundation
@testable import AIServices
@testable import Domain

@Suite("OpenAIService Tests")
struct OpenAIServiceTests {
    @Test("OpenAIService initializes correctly")
    func testInitialization() {
        let service = OpenAIService(apiKey: "test-key")
        #expect(service.provider == .openAI)
    }

    @Test("Missing API key throws error")
    func testMissingAPIKey() async throws {
        let service = OpenAIService(apiKey: "")
        await #expect(throws: AIServiceError.missingAPIKey) {
            _ = try await service.summarize(title: "Test", content: "Content", author: nil)
        }
    }

    @Test("Validation fails with empty key")
    func testValidationWithEmptyKey() async throws {
        let service = OpenAIService(apiKey: "")
        let isValid = try await service.validateConfiguration()
        #expect(isValid == false)
    }
}
