import ProjectDescription
import ProjectDescriptionHelpers

let project = Project(
    name: "EPUBGeneration",
    organizationName: "Epilogue",
    settings: .defaultSettings,
    targets: [
        .target(
            name: "EPUBGeneration",
            destinations: .iOS,
            product: .framework,
            bundleId: "com.epilogue.epubgeneration",
            deploymentTargets: .iOS("18.0"),
            infoPlist: .default,
            sources: ["Sources/EPUBGeneration/**"],
            resources: ["Sources/EPUBGeneration/Resources/**"],
            dependencies: [
                .project(target: "Domain", path: "../Domain"),
                .external(name: "ZIPFoundation")
            ]
        ),
        .target(
            name: "EPUBGenerationTests",
            destinations: .iOS,
            product: .unitTests,
            bundleId: "com.epilogue.epubgenerationtests",
            deploymentTargets: .iOS("18.0"),
            infoPlist: .default,
            sources: ["Tests/EPUBGenerationTests/**"],
            dependencies: [
                .target(name: "EPUBGeneration")
            ]
        )
    ]
)
