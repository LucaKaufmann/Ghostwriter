//
//  EpilogueAppDelegate.swift
//  Epilogue
//
//  Created on 2026-02-07.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import Foundation
import OSLog
import UIKit
import UserNotifications

final class EpilogueAppDelegate: NSObject, UIApplicationDelegate, UNUserNotificationCenterDelegate {
    private let logger = Logger(subsystem: "com.epilogue", category: "AppDelegate")

    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
    ) -> Bool {
        UNUserNotificationCenter.current().delegate = self
        return true
    }

    func application(
        _ application: UIApplication,
        didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data
    ) {
        Task {
            await GhostwriterPushService.registerAPNsDeviceToken(deviceToken)
        }
    }

    func application(
        _ application: UIApplication,
        didFailToRegisterForRemoteNotificationsWithError error: Error
    ) {
        logger.warning("APNs registration failed: \(error.localizedDescription)")
    }

    func application(
        _ application: UIApplication,
        didReceiveRemoteNotification userInfo: [AnyHashable: Any],
        fetchCompletionHandler completionHandler: @escaping (UIBackgroundFetchResult) -> Void
    ) {
        let event = userInfo["event"] as? String
        guard event == "digest_ready" else {
            completionHandler(.noData)
            return
        }

        Task { @MainActor in
            do {
                try await GhostwriterServiceLocator.shared.coordinator?.syncDigests()
                completionHandler(.newData)
            } catch {
                completionHandler(.failed)
            }
        }
    }

    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
        completionHandler([.banner, .sound])
    }
}

