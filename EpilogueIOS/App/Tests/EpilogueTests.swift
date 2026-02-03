import XCTest
@testable import Epilogue

final class EpilogueTests: XCTestCase {
    func testFormatBytes() {
        XCTAssertEqual(SyncPerformanceTracker.formatBytes(512), "512 B")
        XCTAssertEqual(SyncPerformanceTracker.formatBytes(2048), "2.0 KB")
    }
}
