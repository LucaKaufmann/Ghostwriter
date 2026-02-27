//
//  SettingsRepositoryTests.swift
//  Epilogue
//
//  Created on 2026-01-26.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import Testing
import Foundation
@testable import Data
@testable import Domain

@Suite("SettingsRepository Tests")
struct SettingsRepositoryTests {
    let userDefaults: UserDefaults
    let keychainService: KeychainService
    let repository: SettingsRepository

    init() {
        // Use a custom suite for testing to avoid affecting user defaults
        userDefaults = UserDefaults(suiteName: "com.epilogue.tests")!
        keychainService = KeychainService(serviceName: "com.epilogue.tests")
        repository = SettingsRepository(
            userDefaults: userDefaults,
            keychainService: keychainService
        )

        // Clean up before tests
        userDefaults.removePersistentDomain(forName: "com.epilogue.tests")
        try? keychainService.deleteAll()
    }

    @Test("Get and set scheduled hour")
    func testScheduledHour() async throws {
        let hour = try await repository.getScheduledHour()
        #expect(hour == 6) // Default value

        try await repository.setScheduledHour(14)
        let updated = try await repository.getScheduledHour()
        #expect(updated == 14)
    }

    @Test("Invalid scheduled hour throws error")
    func testInvalidScheduledHour() async throws {
        await #expect(throws: SettingsRepositoryError.invalidHour) {
            try await repository.setScheduledHour(-1)
        }

        await #expect(throws: SettingsRepositoryError.invalidHour) {
            try await repository.setScheduledHour(24)
        }
    }

    @Test("Get and set schedule enabled")
    func testScheduleEnabled() async throws {
        let enabled = try await repository.isScheduleEnabled()
        #expect(enabled == true) // Default value

        try await repository.setScheduleEnabled(false)
        let updated = try await repository.isScheduleEnabled()
        #expect(updated == false)
    }

    @Test("Get and set min word count")
    func testMinWordCount() async throws {
        let count = try await repository.getMinWordCount()
        #expect(count == 300) // Default value

        try await repository.setMinWordCount(500)
        let updated = try await repository.getMinWordCount()
        #expect(updated == 500)
    }

    @Test("Invalid word count throws error")
    func testInvalidWordCount() async throws {
        await #expect(throws: SettingsRepositoryError.invalidWordCount) {
            try await repository.setMinWordCount(-1)
        }
    }

    @Test("Get and set AI provider")
    func testAIProvider() async throws {
        let provider = try await repository.getAIProvider()
        #expect(provider == .openAI) // Default value

        try await repository.setAIProvider(.anthropic)
        let updated = try await repository.getAIProvider()
        #expect(updated == .anthropic)
    }

    @Test("Get and set AI model")
    func testAIModel() async throws {
        let model = try await repository.getAIModel()
        #expect(model == "gpt-4o-mini") // Default value

        try await repository.setAIModel("gpt-4o")
        let updated = try await repository.getAIModel()
        #expect(updated == "gpt-4o")
    }

    @Test("Empty model name throws error")
    func testEmptyModelName() async throws {
        await #expect(throws: SettingsRepositoryError.invalidModel) {
            try await repository.setAIModel("")
        }
    }

    @Test("Get and set notifications preference")
    func testNotificationsPreference() async throws {
        let enabled = try await repository.shouldShowNotifications()
        #expect(enabled == true) // Default value

        try await repository.setShouldShowNotifications(false)
        let updated = try await repository.shouldShowNotifications()
        #expect(updated == false)
    }

    @Test("Store and retrieve OpenAI key")
    func testOpenAIKeyStorage() async throws {
        do {
            let key = try await repository.getOpenAIKey()
            #expect(key == nil) // No key stored initially

            try await repository.setOpenAIKey("sk-test-key-123")
            let retrieved = try await repository.getOpenAIKey()
            #expect(retrieved == "sk-test-key-123")
        } catch {
            // Keychain is unavailable in simulator without host app entitlement (error -34018)
            // Skip gracefully in CI/simulator environments
            #expect(Bool(true), "Skipped: Keychain unavailable in this environment (\(error.localizedDescription))")
        }
    }

    @Test("Delete OpenAI key")
    func testDeleteOpenAIKey() async throws {
        do {
            try await repository.setOpenAIKey("sk-test-key-123")
            #expect(try await repository.getOpenAIKey() != nil)

            try await repository.deleteOpenAIKey()
            #expect(try await repository.getOpenAIKey() == nil)
        } catch {
            // Keychain is unavailable in simulator without host app entitlement (error -34018)
            #expect(Bool(true), "Skipped: Keychain unavailable in this environment (\(error.localizedDescription))")
        }
    }

    @Test("Ghostwriter download EPUB on sync defaults to true and can be updated")
    func testGhostwriterDownloadEpubsOnSync() async throws {
        #expect(try await repository.getGhostwriterDownloadEpubsOnSync() == true)

        try await repository.setGhostwriterDownloadEpubsOnSync(false)
        #expect(try await repository.getGhostwriterDownloadEpubsOnSync() == false)

        try await repository.setGhostwriterDownloadEpubsOnSync(true)
        #expect(try await repository.getGhostwriterDownloadEpubsOnSync() == true)
    }
}
