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
