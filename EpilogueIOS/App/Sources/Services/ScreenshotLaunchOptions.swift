//
//  ScreenshotLaunchOptions.swift
//  Epilogue
//
//  Launch argument and environment parsing for deterministic screenshot runs.
//

import Foundation

struct ScreenshotLaunchOptions {
    let isEnabled: Bool
    let fixturePath: String?
    let resetData: Bool

    static var current: ScreenshotLaunchOptions {
        let processInfo = ProcessInfo.processInfo
        let arguments = Set(processInfo.arguments)
        let environment = processInfo.environment

        let isEnabled = arguments.contains("-screenshot-mode") || environment["EPILOGUE_SCREENSHOT_MODE"] == "1"
        let resetData = environment["EPILOGUE_SCREENSHOT_RESET"]?.lowercased() != "false"

        return ScreenshotLaunchOptions(
            isEnabled: isEnabled,
            fixturePath: environment["EPILOGUE_SCREENSHOT_FIXTURE_PATH"],
            resetData: resetData
        )
    }
}
