import Foundation
import ProjectDescription
import ProjectDescriptionHelpers

let marketingVersion = ProcessInfo.processInfo.environment["EPILOGUE_IOS_MARKETING_VERSION"] ?? "1.0.0"
let currentBuildNumber = ProcessInfo.processInfo.environment["EPILOGUE_IOS_BUILD_NUMBER"] ?? "1"

let project = Project(
    name: "Epilogue",
    organizationName: "Epilogue",
    settings: .defaultSettings,
    targets: [
        .target(
            name: "Epilogue",
            destinations: .iOS,
            product: .app,
            bundleId: "com.codable.epilogue",
            deploymentTargets: .iOS("18.0"),
            infoPlist: .extendingDefault(
                with: [
                    "CFBundleShortVersionString": .string(marketingVersion),
                    "CFBundleVersion": .string(currentBuildNumber),
                    "ITSAppUsesNonExemptEncryption": .boolean(false),
                    "UILaunchScreen": [
                        "UIColorName": "",
                        "UIImageName": ""
                    ],
                    "UISupportedInterfaceOrientations": [
                        "UIInterfaceOrientationPortrait"
                    ],
                    "UIUserInterfaceStyle": "Light",
                    "BGTaskSchedulerPermittedIdentifiers": [
                        "com.codable.epilogue.digestgeneration",
                        "com.codable.epilogue.feedRefresh",
                        "com.codable.epilogue.feedSync",
                        "com.codable.epilogue.digestSync"
                    ],
                    "UIBackgroundModes": [
                        "processing",
                        "fetch"
                    ]
                ] as [String: Plist.Value]
            ),
            sources: ["Sources/**"],
            resources: ["Resources/**"],
            dependencies: [
                .project(target: "Domain", path: "../Modules/Domain"),
                .project(target: "Data", path: "../Modules/Data"),
                .project(target: "ContentProcessing", path: "../Modules/ContentProcessing"),
                .project(target: "EPUBGeneration", path: "../Modules/EPUBGeneration"),
                .project(target: "AIServices", path: "../Modules/AIServices"),
                .project(target: "GhostwriterClient", path: "../Modules/GhostwriterClient")
            ]
        ),
        .target(
            name: "EpilogueTests",
            destinations: .iOS,
            product: .unitTests,
            bundleId: "com.codable.epilogue.tests",
            deploymentTargets: .iOS("18.0"),
            infoPlist: .default,
            sources: ["Tests/**"],
            dependencies: [
                .target(name: "Epilogue")
            ]
        ),
        .target(
            name: "EpilogueUITests",
            destinations: .iOS,
            product: .uiTests,
            bundleId: "com.codable.epilogue.uitests",
            deploymentTargets: .iOS("18.0"),
            infoPlist: .default,
            sources: ["UITests/**"],
            dependencies: [
                .target(name: "Epilogue")
            ]
        )
    ]
)
