import ProjectDescription
import ProjectDescriptionHelpers

let project = Project.frameworkModule(
    name: "GhostwriterClient",
    dependencies: [
        .xcframework(path: "../../../shared/build/XCFrameworks/debug/EpilogueShared.xcframework")
    ]
)
