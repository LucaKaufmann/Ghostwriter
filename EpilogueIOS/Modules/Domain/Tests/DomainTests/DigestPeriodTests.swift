//
//  DigestPeriodTests.swift
//  Epilogue
//
//  Created on 2026-02-03.
//

import Testing
@testable import Domain

@Suite("DigestPeriod Tests")
struct DigestPeriodTests {
    @Test("From hour maps to closest period")
    func testFromHourMapping() {
        #expect(DigestPeriod.fromHour(0) == .morning)
        #expect(DigestPeriod.fromHour(9) == .morning)
        #expect(DigestPeriod.fromHour(10) == .noon)
        #expect(DigestPeriod.fromHour(16) == .noon)
        #expect(DigestPeriod.fromHour(17) == .evening)
        #expect(DigestPeriod.fromHour(23) == .evening)
    }

    @Test("Display time formatting")
    func testDisplayTime() {
        #expect(DigestPeriod.morning.displayTime == "7:00")
        #expect(DigestPeriod.noon.displayTime == "12:00")
        #expect(DigestPeriod.evening.displayTime == "18:00")
    }

    @Test("Server period is lowercase")
    func testServerPeriod() {
        #expect(DigestPeriod.morning.serverPeriod == "morning")
        #expect(DigestPeriod.noon.serverPeriod == "noon")
        #expect(DigestPeriod.evening.serverPeriod == "evening")
    }
}

@Suite("TriggerType Tests")
struct TriggerTypeTests {
    @Test("TriggerType display names")
    func testTriggerTypeDisplayName() {
        #expect(TriggerType.scheduled.displayName == "Scheduled")
        #expect(TriggerType.manual.displayName == "Manual")
        #expect(TriggerType.test.displayName == "Test")
        #expect(TriggerType.ghostwriter.displayName == "Ghostwriter")
    }

    @Test("TriggerType icon names")
    func testTriggerTypeIconName() {
        #expect(TriggerType.scheduled.iconName == "clock.arrow.circlepath")
        #expect(TriggerType.manual.iconName == "hand.tap")
        #expect(TriggerType.test.iconName == "testtube.2")
        #expect(TriggerType.ghostwriter.iconName == "cloud.fill")
    }
}
