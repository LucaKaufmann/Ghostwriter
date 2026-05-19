import XCTest
@testable import Epilogue

final class EpilogueTests: XCTestCase {
    func testGhostwriterSettingsVisibleBeforeGhostwriterIsEnabled() {
        XCTAssertTrue(SettingsView.shouldShowGhostwriterSettings(ghostwriterEnabled: false))
    }

    func testDigestSyncRejectsUnsafeRemoteFilenames() {
        let unsafeFilenames = [
            "../escape.epub",
            "/tmp/escape.epub",
            "nested/name.epub",
            "nested\\name.epub",
            ".",
            "..",
            ""
        ]

        for filename in unsafeFilenames {
            XCTAssertThrowsError(try DigestSyncService.validateDigestFilename(filename), filename)
        }
    }

    func testDigestSyncAcceptsBasenameRemoteFilenames() {
        XCTAssertNoThrow(try DigestSyncService.validateDigestFilename("2026-01-26_morning.epub"))
        XCTAssertNoThrow(try DigestSyncService.validateDigestFilename("digest.pdf"))
    }
}
