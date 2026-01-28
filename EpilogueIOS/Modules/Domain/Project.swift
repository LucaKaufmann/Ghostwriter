import ProjectDescription
import ProjectDescriptionHelpers

let project = Project(
    name: "Domain",
    organizationName: "Epilogue",
    settings: .defaultSettings,
    targets: [
        .target(
            name: "Domain",
            destinations: .iOS,
            product: .framework,
            bundleId: "com.epilogue.domain",
            deploymentTargets: .iOS("18.0"),
            infoPlist: .default,
            sources: ["Sources/Domain/**"],
            dependencies: []
        ),
        .target(
            name: "DomainTests",
            destinations: .iOS,
            product: .unitTests,
            bundleId: "com.epilogue.domaintests",
            deploymentTargets: .iOS("18.0"),
            infoPlist: .default,
            sources: ["Tests/DomainTests/**"],
            dependencies: [
                .target(name: "Domain")
            ]
        )
    ]
)
