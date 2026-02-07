import ProjectDescription
import ProjectDescriptionHelpers

let project = Project(
    name: "Epilogue",
    organizationName: "Epilogue",
    settings: .defaultSettings,
    targets: [
        .target(
            name: "Epilogue",
            destinations: .iOS,
            product: .app,
            bundleId: "com.epilogue.app",
            deploymentTargets: .iOS("18.0"),
            infoPlist: .extendingDefault(
                with: [
                    "UILaunchScreen": [
                        "UIColorName": "",
                        "UIImageName": ""
                    ],
                    "UISupportedInterfaceOrientations": [
                        "UIInterfaceOrientationPortrait"
                    ],
                    "UIUserInterfaceStyle": "Light",
                    "BGTaskSchedulerPermittedIdentifiers": [
                        "com.epilogue.app.digestgeneration",
                        "com.epilogue.app.feedSync",
                        "com.epilogue.app.digestSync"
                    ],
                    "UIBackgroundModes": [
                        "processing",
                        "remote-notification"
                    ]
                ]
            ),
            sources: ["Sources/**"],
            resources: ["Resources/**"],
            entitlements: "Epilogue.entitlements",
            dependencies: [
                .project(target: "Domain", path: "../Modules/Domain"),
                .project(target: "Data", path: "../Modules/Data"),
                .project(target: "ContentProcessing", path: "../Modules/ContentProcessing"),
                .project(target: "EPUBGeneration", path: "../Modules/EPUBGeneration"),
                .project(target: "AIServices", path: "../Modules/AIServices"),
                .project(target: "GhostwriterClient", path: "../Modules/GhostwriterClient")
            ],
            settings: .settings(
                base: [:],
                configurations: [
                    .debug(name: .debug, settings: ["APS_ENVIRONMENT": "development"]),
                    .release(name: .release, settings: ["APS_ENVIRONMENT": "production"])
                ]
            )
        ),
        .target(
            name: "EpilogueTests",
            destinations: .iOS,
            product: .unitTests,
            bundleId: "com.epilogue.apptests",
            deploymentTargets: .iOS("18.0"),
            infoPlist: .default,
            sources: ["Tests/**"],
            dependencies: [
                .target(name: "Epilogue")
            ]
        )
    ]
)
