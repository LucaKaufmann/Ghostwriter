import ProjectDescription
import ProjectDescriptionHelpers

let project = Project(
    name: "AIServices",
    organizationName: "Epilogue",
    settings: .defaultSettings,
    targets: [
        .target(
            name: "AIServices",
            destinations: .iOS,
            product: .framework,
            bundleId: "com.epilogue.aiservices",
            deploymentTargets: .iOS("18.0"),
            infoPlist: .default,
            sources: ["Sources/AIServices/**"],
            dependencies: [
                .project(target: "Domain", path: "../Domain")
            ]
        ),
        .target(
            name: "AIServicesTests",
            destinations: .iOS,
            product: .unitTests,
            bundleId: "com.epilogue.aiservicestests",
            deploymentTargets: .iOS("18.0"),
            infoPlist: .default,
            sources: ["Tests/AIServicesTests/**"],
            dependencies: [
                .target(name: "AIServices")
            ]
        )
    ]
)
