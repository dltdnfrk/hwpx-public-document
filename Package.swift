// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "PublicDocumentApp",
    platforms: [.macOS(.v13)],
    products: [
        .executable(name: "PublicDocumentApp", targets: ["PublicDocumentApp"]),
    ],
    targets: [
        .executableTarget(name: "PublicDocumentApp"),
    ]
)
