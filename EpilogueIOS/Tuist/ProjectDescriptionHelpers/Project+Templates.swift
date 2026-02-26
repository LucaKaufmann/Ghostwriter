import ProjectDescription

// MARK: - Project Templates

extension Project {
    /// Creates a feature module project with main and interface targets
    public static func featureModule(
        name: String,
        dependencies: [TargetDependency] = [],
        hasInterface: Bool = true
    ) -> Project {
        let interfaceTarget: Target? = hasInterface ? .target(
            name: "\(name)Interface",
            destinations: .iOS,
            product: .framework,
            bundleId: "com.epilogue.\(name.lowercased())interface",
            deploymentTargets: .iOS("18.0"),
            infoPlist: .default,
            sources: ["Sources/\(name)Interface/**"],
            dependencies: []
        ) : nil

        let mainTarget = Target.target(
            name: name,
            destinations: .iOS,
            product: .framework,
            bundleId: "com.epilogue.\(name.lowercased())",
            deploymentTargets: .iOS("18.0"),
            infoPlist: .default,
            sources: ["Sources/\(name)/**"],
            dependencies: hasInterface ?
                [.target(name: "\(name)Interface")] + dependencies :
                dependencies
        )

        let testTarget = Target.target(
            name: "\(name)Tests",
            destinations: .iOS,
            product: .unitTests,
            bundleId: "com.epilogue.\(name.lowercased())tests",
            deploymentTargets: .iOS("18.0"),
            infoPlist: .default,
            sources: ["Tests/\(name)Tests/**"],
            dependencies: [.target(name: name)]
        )

        var targets = [mainTarget, testTarget]
        if let interface = interfaceTarget {
            targets.insert(interface, at: 0)
        }

        return Project(
            name: name,
            organizationName: "Epilogue",
            targets: targets
        )
    }

    /// Creates a framework module project without interface separation
    public static func frameworkModule(
        name: String,
        dependencies: [TargetDependency] = [],
        externalDependencies: [String] = []
    ) -> Project {
        let externalDeps = externalDependencies.map { TargetDependency.external(name: $0) }

        let mainTarget = Target.target(
            name: name,
            destinations: .iOS,
            product: .framework,
            bundleId: "com.epilogue.\(name.lowercased())",
            deploymentTargets: .iOS("18.0"),
            infoPlist: .default,
            sources: ["Sources/\(name)/**"],
            dependencies: dependencies + externalDeps
        )

        let testTarget = Target.target(
            name: "\(name)Tests",
            destinations: .iOS,
            product: .unitTests,
            bundleId: "com.epilogue.\(name.lowercased())tests",
            deploymentTargets: .iOS("18.0"),
            infoPlist: .default,
            sources: ["Tests/\(name)Tests/**"],
            dependencies: [.target(name: name)]
        )

        return Project(
            name: name,
            organizationName: "Epilogue",
            targets: [mainTarget, testTarget]
        )
    }
}

// MARK: - Settings Helpers

extension Settings {
    public static var defaultSettings: Settings {
        return .settings(
            base: [
                "SWIFT_VERSION": "5.9",
                "IPHONEOS_DEPLOYMENT_TARGET": "18.0",
                "ENABLE_PREVIEWS": "YES",
                "MARKETING_VERSION": "1.0.0",
                "CURRENT_PROJECT_VERSION": "1",
                "DEVELOPMENT_TEAM": "6Y9C574C9M",
                "CODE_SIGN_STYLE": "Automatic"
            ],
            configurations: [
                .debug(name: .debug),
                .release(name: .release)
            ]
        )
    }
}
