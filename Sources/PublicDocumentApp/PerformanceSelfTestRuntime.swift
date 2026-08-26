import CryptoKit
import Darwin
import Foundation

extension PerformanceSelfTest {
    static func executionIdentity() throws -> PerformanceExecutionIdentity {
        let bundle = Bundle.main
        let appRoot = bundle.bundleURL.standardizedFileURL
        guard appRoot.pathExtension == "app",
              bundle.bundleIdentifier == "com.muni.public-document" else {
            throw ExportError.invalidPackage("AC-09 성능 증거는 패키지된 PublicDocument.app에서 실행해야 합니다.")
        }
        let executableRelativePath = "Contents/MacOS/PublicDocumentApp"
        let genOfficeManifestRelativePath = "Contents/Resources/GenOffice/runtime-manifest.json"
        let genOfficeBundleRelativePath = "Contents/Resources/GenOffice/public-document-genoffice.js"
        let nodeRelativePath = "Contents/Resources/Engines/node"
        let rhwpRelativePath = "Contents/Resources/Engines/rhwp"
        let executable = appRoot.appendingPathComponent(executableRelativePath)
        guard bundle.executableURL?.resolvingSymlinksInPath().standardizedFileURL
                == executable.resolvingSymlinksInPath().standardizedFileURL else {
            throw ExportError.invalidPackage("AC-09 패키지 실행 파일 경로")
        }
        return PerformanceExecutionIdentity(
            bundleIdentifier: bundle.bundleIdentifier ?? "unavailable",
            bundleVersion: bundle.object(forInfoDictionaryKey: "CFBundleVersion") as? String
                ?? "unavailable",
            applicationVersion: bundle.object(
                forInfoDictionaryKey: "CFBundleShortVersionString"
            ) as? String ?? "unavailable",
            bundleExecutableRelativePath: executableRelativePath,
            executableSHA256: try hashFile(executable),
            genOfficeRuntimeManifestRelativePath: genOfficeManifestRelativePath,
            genOfficeRuntimeManifestSHA256: try hashFile(
                appRoot.appendingPathComponent(genOfficeManifestRelativePath)
            ),
            genOfficeBundleRelativePath: genOfficeBundleRelativePath,
            genOfficeBundleSHA256: try hashFile(
                appRoot.appendingPathComponent(genOfficeBundleRelativePath)
            ),
            nodeExecutableRelativePath: nodeRelativePath,
            nodeExecutableSHA256: try hashFile(appRoot.appendingPathComponent(nodeRelativePath)),
            rhwpExecutableRelativePath: rhwpRelativePath,
            rhwpExecutableSHA256: try hashFile(appRoot.appendingPathComponent(rhwpRelativePath))
        )
    }

    static func profileURL() -> URL {
        let bundled = Bundle.main.resourceURL?
            .appendingPathComponent("Performance/performance-profile-1.0.0.json")
        let local = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
            .appendingPathComponent("Resources/Performance/performance-profile-1.0.0.json")
        return bundled.flatMap { FileManager.default.fileExists(atPath: $0.path) ? $0 : nil } ?? local
    }

    static func renderedPageCount(format: DocumentFormat, artifact: URL) throws -> Int? {
        guard [.hwpx, .hwp].contains(format) else { return nil }
        let bundled = Bundle.main.resourceURL?.appendingPathComponent("Engines/rhwp")
        let local = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
            .appendingPathComponent("Resources/Engines/rhwp")
        let engine = bundled.flatMap {
            FileManager.default.isExecutableFile(atPath: $0.path) ? $0 : nil
        } ?? local
        let process = Process()
        let output = Pipe()
        process.executableURL = engine
        process.arguments = ["info", artifact.path, "--json"]
        process.standardOutput = output
        process.standardError = FileHandle.standardError
        try process.run()
        let data = output.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        guard process.terminationStatus == 0 else {
            throw ExportError.rhwpFailed("성능 fixture 쪽수 검증 실패")
        }
        return try JSONDecoder().decode(RhwpPageInfo.self, from: data).pageCount
    }

    static func environment() -> PerformanceEnvironment {
        #if arch(arm64)
        let architecture = "arm64"
        #else
        let architecture = "unsupported"
        #endif
        return PerformanceEnvironment(
            modelIdentifier: sysctlString("hw.model"),
            processor: sysctlString("machdep.cpu.brand_string"),
            architecture: architecture,
            physicalMemoryBytes: ProcessInfo.processInfo.physicalMemory,
            osVersion: ProcessInfo.processInfo.operatingSystemVersionString,
            osBuild: sysctlString("kern.osversion"),
            applicationVersion: Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "0.1.0",
            recordedAt: ISO8601DateFormatter().string(from: Date())
        )
    }

    static func sysctlString(_ name: String) -> String {
        var size = 0
        guard sysctlbyname(name, nil, &size, nil, 0) == 0, size > 0 else { return "unavailable" }
        var value = [CChar](repeating: 0, count: size)
        guard sysctlbyname(name, &value, &size, nil, 0) == 0 else { return "unavailable" }
        return String(cString: value)
    }

    static func hash(_ data: Data) -> String {
        "sha256:" + SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }

    static func hashFile(_ url: URL) throws -> String {
        guard FileManager.default.isReadableFile(atPath: url.path) else {
            throw ExportError.invalidPackage("AC-09 패키지 런타임 파일: \(url.lastPathComponent)")
        }
        return hash(try Data(contentsOf: url))
    }
}
