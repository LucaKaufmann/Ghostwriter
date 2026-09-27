import XCTest

final class EpilogueScreenshotTests: XCTestCase {
    private var app: XCUIApplication!

    override func setUpWithError() throws {
        continueAfterFailure = false

        app = XCUIApplication()
        app.launchArguments += ["-ui-testing", "-screenshot-mode"]

        if let fixturePath = ProcessInfo.processInfo.environment["EPILOGUE_SCREENSHOT_FIXTURE_PATH"], !fixturePath.isEmpty {
            app.launchEnvironment["EPILOGUE_SCREENSHOT_FIXTURE_PATH"] = fixturePath
        }

        if let outputPath = ProcessInfo.processInfo.environment["EPILOGUE_SCREENSHOT_OUTPUT_DIR"], !outputPath.isEmpty {
            app.launchEnvironment["EPILOGUE_SCREENSHOT_OUTPUT_DIR"] = outputPath
        }

        app.launch()
    }

    func testCaptureStoreScreenshots() throws {
        XCTAssertTrue(waitForExists(app.tabBars.firstMatch), "Tab bar did not appear")

        capture(name: "01-feeds")

        tapTab("History")
        XCTAssertTrue(waitForExists(app.navigationBars["Digest History"]), "Digest History screen did not load")
        capture(name: "02-history")

        let firstDigestCell = app.tables.cells.firstMatch.exists ? app.tables.cells.firstMatch : app.collectionViews.cells.firstMatch
        XCTAssertTrue(waitForExists(firstDigestCell), "No digest row found for detail screenshot")
        firstDigestCell.tap()

        XCTAssertTrue(waitForExists(app.navigationBars.buttons["Back"]), "Digest detail screen did not load")
        capture(name: "03-reader")

        app.navigationBars.buttons["Back"].tap()

        tapTab("Settings")
        XCTAssertTrue(waitForExists(app.navigationBars["Settings"]), "Settings screen did not load")
        capture(name: "04-settings")
    }

    func testFeedResolutionFixture() throws {
        app.terminate()
        app.launchArguments += ["-feed-v2-ui-fixture"]
        app.launch()
        XCTAssertTrue(waitForExists(app.staticTexts["Web headline"]))
        XCTAssertTrue(waitForExists(app.staticTexts["Rejected feed"]))
        XCTAssertTrue(waitForExists(app.staticTexts["Missing feed"]))
        XCTAssertTrue(waitForExists(app.staticTexts["Removed locally"]))
        capture(name: "feed-v2-attention")

        app.staticTexts["Web headline"].tap()
        XCTAssertTrue(waitForExists(app.navigationBars["Resolve feed"]))
        XCTAssertTrue(waitForExists(app.buttons["Apply mine"]))
        capture(name: "feed-v2-conflict")
        app.buttons["Close"].tap()

        app.staticTexts["Rejected feed"].tap()
        XCTAssertTrue(waitForExists(app.buttons["Correct and retry"]))
        capture(name: "feed-v2-rejected")
        app.buttons["Close"].tap()

        app.staticTexts["Missing feed"].tap()
        XCTAssertTrue(waitForExists(app.buttons["Add to server"]))
        capture(name: "feed-v2-absent")
        app.buttons["Close"].tap()

        app.staticTexts["https://example.test/delete.xml"].tap()
        XCTAssertTrue(waitForExists(app.buttons["Delete anyway"]))
        capture(name: "feed-v2-delete")
        app.buttons["Close"].tap()

        app.staticTexts["https://example.test/rejected-delete.xml"].tap()
        XCTAssertTrue(waitForExists(app.buttons["Discard proposal"]))
        XCTAssertFalse(app.textFields["Corrected title"].exists)
        XCTAssertFalse(app.buttons["Correct and retry"].exists)
        capture(name: "feed-v2-rejected-delete")
    }

    func testRemoteDigestArtifactAvailabilityFixture() throws {
        app.terminate()
        app.launchArguments += ["-feed-v2-ui-fixture", "-digest-artifact-ui-fixture"]
        app.launch()
        tapTab("History")

        let empty = app.staticTexts["No EPUB for empty digest"]
        let indexed = app.staticTexts["EPUB not downloaded"]
        XCTAssertTrue(waitForExists(empty))
        XCTAssertTrue(waitForExists(indexed))
        capture(name: "sync-status-history")

        empty.swipeRight()
        XCTAssertFalse(app.buttons["EPUB"].exists)
        XCTAssertFalse(app.buttons["PDF"].exists)
        if !app.staticTexts["No articles in this digest"].exists {
            empty.tap()
        }
        XCTAssertTrue(waitForExists(app.staticTexts["No articles in this digest"]))
        XCTAssertFalse(app.buttons["Share"].exists)
        capture(name: "sync-status-empty-detail")

        app.navigationBars.buttons["Digest History"].tap()
        indexed.swipeRight()
        XCTAssertTrue(waitForExists(app.buttons["EPUB"]))
    }

    private func tapTab(_ title: String) {
        let button = app.tabBars.buttons[title]
        XCTAssertTrue(waitForExists(button), "Tab \(title) not found")
        button.tap()
    }

    @discardableResult
    private func waitForExists(_ element: XCUIElement, timeout: TimeInterval = 10) -> Bool {
        element.waitForExistence(timeout: timeout)
    }

    private func capture(name: String) {
        let screenshot = XCUIScreen.main.screenshot()
        let attachment = XCTAttachment(screenshot: screenshot)
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)

        let outputDirectory = ProcessInfo.processInfo.environment["EPILOGUE_SCREENSHOT_OUTPUT_DIR"]
            ?? FileManager.default.currentDirectoryPath + "/artifacts/screenshots"

        let outputURL = URL(fileURLWithPath: outputDirectory, isDirectory: true)
        try? FileManager.default.createDirectory(at: outputURL, withIntermediateDirectories: true)
        let fileURL = outputURL.appendingPathComponent("\(name).png")
        try? screenshot.pngRepresentation.write(to: fileURL)
    }
}
