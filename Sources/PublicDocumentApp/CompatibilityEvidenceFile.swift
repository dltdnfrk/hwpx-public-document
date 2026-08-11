import CryptoKit
import Foundation

enum CompatibilityEvidenceFileKind {
    case artifact
    case observation
}

enum CompatibilityEvidenceFile {
    static func data(
        relativePath: String,
        root: URL,
        kind: CompatibilityEvidenceFileKind
    ) throws -> Data {
        guard !relativePath.isEmpty,
              !relativePath.hasPrefix("/"),
              !NSString(string: relativePath).pathComponents.contains("..")
        else { throw error(kind: kind, detail: "evidence path") }

        let fileManager = FileManager.default
        let resolvedRoot = root.standardizedFileURL.resolvingSymlinksInPath()
        var rootIsDirectory = ObjCBool(false)
        guard fileManager.fileExists(
            atPath: resolvedRoot.path, isDirectory: &rootIsDirectory
        ), rootIsDirectory.boolValue else {
            throw error(kind: kind, detail: "evidence root is missing")
        }

        let candidate = resolvedRoot.appendingPathComponent(relativePath).standardizedFileURL
        var candidateIsDirectory = ObjCBool(false)
        guard fileManager.fileExists(
            atPath: candidate.path, isDirectory: &candidateIsDirectory
        ), !candidateIsDirectory.boolValue else {
            throw error(kind: kind, detail: "evidence file is missing")
        }
        let resolvedCandidate = candidate.resolvingSymlinksInPath().standardizedFileURL
        guard resolvedCandidate.path.hasPrefix(resolvedRoot.path + "/") else {
            throw error(kind: kind, detail: "evidence path escapes root")
        }
        return try Data(contentsOf: resolvedCandidate)
    }

    static func sha256(_ data: Data) -> String {
        "sha256:" + SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }

    private static func error(
        kind: CompatibilityEvidenceFileKind,
        detail: String
    ) -> CompatibilityEvidenceError {
        switch kind {
        case .artifact:
            return .invalidCorpus(detail)
        case .observation:
            return .invalidObservation(detail)
        }
    }
}
