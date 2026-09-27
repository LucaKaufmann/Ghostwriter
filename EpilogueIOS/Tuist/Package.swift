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
        .package(url: "https://github.com/nmdias/FeedKit.git", exact: "9.1.2"),

        // HTML parsing and manipulation
        .package(url: "https://github.com/scinfu/SwiftSoup.git", exact: "2.13.9"),

        // ZIP archive creation for EPUB generation
        .package(url: "https://github.com/weichsel/ZIPFoundation.git", exact: "0.9.20")
    ]
)
