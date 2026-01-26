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
                        "com.epilogue.app.digestgeneration"
                    ],
                    "UIBackgroundModes": [
                        "processing"
                    ]
                ]
            ),
            sources: ["Sources/**"],
            resources: ["Resources/**"],
            dependencies: [
                .project(target: "Domain", path: "../Modules/Domain"),
                .project(target: "Data", path: "../Modules/Data"),
                .project(target: "GhostwriterClient", path: "../Modules/GhostwriterClient")
            ]
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
