// swift-tools-version: 5.9
import PackageDescription

#if TUIST
    import ProjectDescription

    let packageSettings = PackageSettings(
        productTypes: [
            "FeedKit": .framework,
            "SwiftSoup": .framework,
            "ZIPFoundation": .framework
        ]
    )
#endif

let package = Package(
    name: "EpiloguePackages",
    dependencies: [
        // RSS/Atom feed parsing
        .package(url: "https://github.com/nmdias/FeedKit.git", from: "9.1.2"),

        // HTML parsing and manipulation
        .package(url: "https://github.com/scinfu/SwiftSoup.git", from: "2.7.1"),

        // ZIP archive creation for EPUB generation
        .package(url: "https://github.com/weichsel/ZIPFoundation.git", from: "0.9.19")
    ]
)
