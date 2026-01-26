import ProjectDescription
import ProjectDescriptionHelpers

let project = Project(
    name: "ContentProcessing",
    organizationName: "Epilogue",
    settings: .defaultSettings,
    targets: [
        .target(
            name: "ContentProcessing",
            destinations: .iOS,
            product: .framework,
            bundleId: "com.epilogue.contentprocessing",
            deploymentTargets: .iOS("18.0"),
            infoPlist: .default,
            sources: ["Sources/ContentProcessing/**"],
            dependencies: [
                .project(target: "Domain", path: "../Domain"),
                .external(name: "FeedKit"),
                .external(name: "SwiftSoup")
            ]
        ),
        .target(
            name: "ContentProcessingTests",
            destinations: .iOS,
            product: .unitTests,
            bundleId: "com.epilogue.contentprocessingtests",
            deploymentTargets: .iOS("18.0"),
            infoPlist: .default,
            sources: ["Tests/ContentProcessingTests/**"],
            dependencies: [
                .target(name: "ContentProcessing")
            ]
        )
    ]
)
