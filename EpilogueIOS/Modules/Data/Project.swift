import ProjectDescription
import ProjectDescriptionHelpers

let project = Project(
    name: "Data",
    organizationName: "Epilogue",
    settings: .defaultSettings,
    targets: [
        .target(
            name: "Data",
            destinations: .iOS,
            product: .framework,
            bundleId: "com.epilogue.data",
            deploymentTargets: .iOS("18.0"),
            infoPlist: .default,
            sources: ["Sources/Data/**"],
            dependencies: [
                .project(target: "Domain", path: "../Domain")
            ]
        ),
        .target(
            name: "DataTests",
            destinations: .iOS,
            product: .unitTests,
            bundleId: "com.epilogue.datatests",
            deploymentTargets: .iOS("18.0"),
            infoPlist: .default,
            sources: ["Tests/DataTests/**"],
            dependencies: [
                .target(name: "Data")
            ]
        )
    ]
)
