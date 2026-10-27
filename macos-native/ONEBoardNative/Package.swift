// swift-tools-version: 5.10

import PackageDescription

let package = Package(
    name: "ONEBoardNative",
    platforms: [
        .macOS(.v14)
    ],
    products: [
        .executable(name: "ONEBoardNative", targets: ["ONEBoardNative"])
    ],
    targets: [
        .executableTarget(
            name: "ONEBoardNative"
        )
    ]
)
