import CryptoKit
import Foundation

private struct GenOfficeHashEntry: Decodable {
    let path: String
    let sha256: String
}

private struct GenOfficeNodeManifest: Decodable {
    let version: String
    let sourcePath: String
    let sha256: String
    let architecture: String
}

private struct GenOfficeUpstreamManifest: Decodable {
    let commit: String
}

private struct GenOfficeRuntimeManifest: Decodable {
    let upstream: GenOfficeUpstreamManifest
    let inputs: [GenOfficeHashEntry]
    let outputs: [GenOfficeHashEntry]
    let node: GenOfficeNodeManifest
}

private struct GenOfficeCLIReceipt: Decodable {
    let schemaVersion: Int
    let inputSha256: String
    let outputSha256: String
    let blockCount: Int
    let preservedPartNames: [String]
    let savedAt: String
    let upstreamCommit: String
    let packageName: String
}

struct GenOfficeDocxNormalization {
    let data: Data
    let engineIdentity: ExportEngineIdentity
}

struct GenOfficeDocxAdapter {
    private static let cliPath = "GenOffice/genoffice-docx-normalize.cjs"
    private static let manifestPath = "GenOffice/runtime-manifest.json"
    private let fileManager: FileManager

    init(fileManager: FileManager = .default) {
        self.fileManager = fileManager
    }

    func normalize(
        seed: Data,
        workingDirectory: URL,
        savedAt: String
    ) throws -> GenOfficeDocxNormalization {
        guard ISO8601DateFormatter().date(from: savedAt) != nil else {
            throw ExportError.genOfficeDocxFailed("결정적 savedAt ISO-8601")
        }
        let runtime = try verifiedRuntime()
        let work = workingDirectory.appendingPathComponent(".genoffice-\(UUID().uuidString)")
        try fileManager.createDirectory(at: work, withIntermediateDirectories: false)
        defer { try? fileManager.removeItem(at: work) }
        let input = work.appendingPathComponent("input.docx")
        let output = work.appendingPathComponent("output.docx")
        try seed.write(to: input, options: .withoutOverwriting)
        let receipt = try run(runtime: runtime, input: input, output: output, savedAt: savedAt)
        let normalized = try Data(contentsOf: output)
        try validates(receipt: receipt, seed: seed, normalized: normalized, runtime: runtime, savedAt: savedAt)
        return GenOfficeDocxNormalization(
            data: normalized,
            engineIdentity: runtime.identity(savedAt: savedAt)
        )
    }

    private func verifiedRuntime() throws -> VerifiedGenOfficeRuntime {
        for root in resourceRoots() {
            if let runtime = try runtime(at: root) { return runtime }
        }
        throw ExportError.missingGenOfficeDocxEngine
    }

    private func resourceRoots() -> [URL] {
        let local = URL(fileURLWithPath: fileManager.currentDirectoryPath)
            .appendingPathComponent("Resources", isDirectory: true)
        let bundled = Bundle.main.resourceURL
        return [bundled, local].compactMap { $0 }
    }

    private func runtime(at resourceRoot: URL) throws -> VerifiedGenOfficeRuntime? {
        let manifestURL = resourceRoot.appendingPathComponent(Self.manifestPath)
        guard fileManager.fileExists(atPath: manifestURL.path) else { return nil }
        let manifest: GenOfficeRuntimeManifest
        do {
            manifest = try JSONDecoder().decode(GenOfficeRuntimeManifest.self, from: Data(contentsOf: manifestURL))
        } catch {
            throw ExportError.missingGenOfficeDocxEngine
        }
        guard manifest.node.architecture == "arm64",
              let cli = verifiedURL(for: Self.cliPath, entries: manifest.outputs, root: resourceRoot),
              let node = verifiedURL(for: manifest.node.sourcePath, expectedSHA256: manifest.node.sha256, root: resourceRoot),
              fileManager.isExecutableFile(atPath: node.path)
        else { throw ExportError.missingGenOfficeDocxEngine }
        for entry in manifest.outputs where entry.path.hasPrefix("GenOffice/") {
            guard verifiedURL(for: entry.path, expectedSHA256: entry.sha256, root: resourceRoot) != nil else {
                throw ExportError.missingGenOfficeDocxEngine
            }
        }
        return VerifiedGenOfficeRuntime(
            node: node,
            cli: cli,
            upstreamCommit: manifest.upstream.commit,
            nodeVersion: manifest.node.version,
            nodeArchitecture: manifest.node.architecture,
            nodeSHA256: prefixedHash(manifest.node.sha256),
            cliSHA256: prefixedHash(try hash(of: cli))
        )
    }

    private func verifiedURL(
        for path: String,
        entries: [GenOfficeHashEntry],
        root: URL
    ) -> URL? {
        guard let entry = entries.first(where: { $0.path == path }) else { return nil }
        return verifiedURL(for: path, expectedSHA256: entry.sha256, root: root)
    }

    private func verifiedURL(for path: String, expectedSHA256: String, root: URL) -> URL? {
        guard let relative = resourceRelativePath(path) else { return nil }
        let candidate = root.appendingPathComponent(relative)
        guard fileManager.fileExists(atPath: candidate.path),
              (try? hash(of: candidate)) == unprefixedHash(expectedSHA256)
        else { return nil }
        return candidate
    }

    private func run(
        runtime: VerifiedGenOfficeRuntime,
        input: URL,
        output: URL,
        savedAt: String
    ) throws -> GenOfficeCLIReceipt {
        let process = Process()
        let standardOutput = Pipe()
        let diagnosticURL = input.deletingLastPathComponent().appendingPathComponent("diagnostic.log")
        fileManager.createFile(atPath: diagnosticURL.path, contents: nil)
        let standardError = try FileHandle(forWritingTo: diagnosticURL)
        defer { try? standardError.close() }
        process.executableURL = runtime.node
        process.arguments = [runtime.cli.path, input.path, output.path, savedAt]
        process.environment = [:]
        process.standardOutput = standardOutput
        process.standardError = standardError
        try process.run()
        let stdout = standardOutput.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        try standardError.synchronize()
        let diagnostic = String(data: try Data(contentsOf: diagnosticURL), encoding: .utf8) ?? ""
        guard process.terminationStatus == 0 else { throw ExportError.genOfficeDocxFailed(diagnostic) }
        guard stdout.split(separator: 0x0a).count == 1,
              let receipt = try? JSONDecoder().decode(GenOfficeCLIReceipt.self, from: stdout)
        else { throw ExportError.genOfficeDocxFailed("정규화 영수증 형식") }
        return receipt
    }

    private func validates(
        receipt: GenOfficeCLIReceipt,
        seed: Data,
        normalized: Data,
        runtime: VerifiedGenOfficeRuntime,
        savedAt: String
    ) throws {
        guard receipt.schemaVersion == 1,
              receipt.blockCount >= 0,
              receipt.savedAt == savedAt,
              receipt.upstreamCommit == runtime.upstreamCommit,
              receipt.packageName == "@genoffice/docx-engine",
              normalizedHash(receipt.inputSha256) == hash(data: seed),
              normalizedHash(receipt.outputSha256) == hash(data: normalized),
              Set(["customXml/item1.xml", "word/document.xml"]).isSubset(of: receipt.preservedPartNames)
        else { throw ExportError.genOfficeDocxFailed("정규화 영수증 바인딩") }
    }

    private func resourceRelativePath(_ path: String) -> String? {
        let prefix = path.hasPrefix("Resources/") ? "Resources/" : ""
        let relative = String(path.dropFirst(prefix.count))
        let components = relative.split(separator: "/")
        guard !components.isEmpty, !components.contains(".."), !components.contains(".") else { return nil }
        return relative
    }

    private func hash(of url: URL) throws -> String {
        try hash(data: Data(contentsOf: url))
    }

    private func hash(data: Data) -> String {
        SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }

    private func normalizedHash(_ value: String) -> String {
        unprefixedHash(value)
    }

    private func unprefixedHash(_ value: String) -> String {
        value.replacingOccurrences(of: "sha256:", with: "")
    }

    private func prefixedHash(_ value: String) -> String {
        "sha256:\(unprefixedHash(value))"
    }
}

private struct VerifiedGenOfficeRuntime {
    let node: URL
    let cli: URL
    let upstreamCommit: String
    let nodeVersion: String
    let nodeArchitecture: String
    let nodeSHA256: String
    let cliSHA256: String

    func identity(savedAt: String) -> ExportEngineIdentity {
        ExportEngineIdentity(
            engine: "genoffice-docx-normalize",
            packageName: "@genoffice/docx-engine",
            upstreamCommit: upstreamCommit,
            nodeVersion: nodeVersion,
            nodeArchitecture: nodeArchitecture,
            nodeSHA256: nodeSHA256,
            cliSHA256: cliSHA256,
            savedAt: savedAt
        )
    }
}
