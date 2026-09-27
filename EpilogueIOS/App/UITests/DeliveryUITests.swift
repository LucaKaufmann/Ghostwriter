import XCTest

final class DeliveryUITests: XCTestCase {
    func testLocalDeliveryOutcomesAndExplicitRegeneration() throws {
        for (outcome, expected) in [
            ("complete", "Complete: 1 article"),
            ("partial", "Partial: 1 article"),
            ("empty", "No new articles to include"),
            ("deferred", "No articles included; more remain for the next edition"),
            ("failed", "Generation failed: 1 issue")
        ] {
            let app = XCUIApplication()
            app.launchArguments = ["-ui-testing", "-screenshot-mode", "-delivery-ui-\(outcome)"]
            app.launch()
            let settings = app.tabBars.buttons["Settings"]
            XCTAssertTrue(settings.waitForExistence(timeout: 10))
            settings.tap()
            XCTAssertTrue(app.navigationBars["Settings"].waitForExistence(timeout: 10))
            let regenerate = app.buttons["Regenerate including delivered articles"]
            for _ in 0..<6 where !regenerate.exists {
                app.collectionViews.firstMatch.swipeUp()
            }
            XCTAssertTrue(regenerate.waitForExistence(timeout: 10))
            XCTAssertTrue(app.descendants(matching: .any)
                .matching(NSPredicate(format: "label CONTAINS %@", expected))
                .firstMatch.waitForExistence(timeout: 10))
            let screenshot = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
            screenshot.name = "delivery-\(outcome)"
            screenshot.lifetime = .keepAlways
            add(screenshot)
            app.terminate()
        }
    }
}
