import CryptoKit
import Darwin
import Foundation

final class BatchExportStore {
    private static let progressTotal = 4
    private static let stateDirectoryName = ".public-document-studio-exports"
    private let fileManager: FileManager
    private let encoder: JSONEncoder
    private let decoder: JSONDecoder

    init(fileManager: FileManager) {
        self.fileManager = fileManager
        encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        decoder = JSONDecoder()
    }

    func prepare(_ operationRoot: URL) throws {
        try fileManager.createDirectory(at: operationRoot, withIntermediateDirectories: true)
        try fileManager.createDirectory(at: snapshotsRoot(operationRoot), withIntermediateDirectories: true)
        try fileManager.createDirectory(at: stagingRoot(operationRoot), withIntermediateDirectories: true)
    }

    func initialManifest(
        request: BatchExportRequest,
        operationRoot: URL,
        selectedFormats: [DocumentFormat]
    ) throws -> BatchExportManifest {
        let documentIDs = request.documents.map { $0.project.documentID }
        guard Set(documentIDs).count == documentIDs.count else {
            throw BatchExportError.missingSnapshot("중복 문서 ID")
        }
        var items: [BatchExportItem] = []
        for document in request.documents {
            guard !document.fileStem.isEmpty,
                  !document.fileStem.contains("/"),
                  document.fileStem != ".",
                  document.fileStem != ".."
            else { throw BatchExportError.invalidFileStem(document.fileStem) }
            let snapshotData = try encoder.encode(document.project)
            let snapshot = snapshotsRoot(operationRoot)
                .appendingPathComponent("\(document.project.documentID).json")
            try snapshotData.write(to: snapshot, options: .atomic)
            let snapshotHash = "sha256:" + SHA256.hash(data: snapshotData)
                .map { String(format: "%02x", $0) }
                .joined()
            for format in selectedFormats {
                items.append(BatchExportItem(
                    itemID: "\(document.project.documentID)-\(format.rawValue)",
                    documentID: document.project.documentID,
                    documentDisplayName: document.project.title.isEmpty
                        ? document.project.documentID
                        : document.project.title,
                    snapshotRevisionID: document.project.currentRevisionID,
                    snapshotHash: snapshotHash,
                    format: format,
                    destinationFile: "\(document.fileStem).\(format.fileExtension)",
                    state: .queued,
                    progressCompleted: 1,
                    progressTotal: Self.progressTotal,
                    artifactHash: nil,
                    publicationIntent: nil,
                    diagnosticCode: "",
                    diagnosticMessage: ""
                ))
            }
        }
        return BatchExportManifest(
            schemaVersion: 2,
            operationID: request.operationID,
            retryOfOperationID: request.retryOfOperationID,
            state: .running,
            cleanupState: .pending,
            manifestPath: manifestURL(operationRoot).path,
            selectedFormats: selectedFormats,
            flatteningConsent: DocumentFormat.allCases.filter(request.flatteningConsent.contains),
            items: items
        )
    }

    func retryRequest(
        destination: URL,
        previousOperationID: String,
        newOperationID: String
    ) throws -> BatchExportRequest {
        let previousRoot = operationRoot(for: destination, operationID: previousOperationID)
        let manifest = try decoder.decode(
            BatchExportManifest.self,
            from: Data(contentsOf: manifestURL(previousRoot))
        )
        var seenDocumentIDs: Set<String> = []
        var documents: [BatchDocumentInput] = []
        for item in manifest.items where seenDocumentIDs.insert(item.documentID).inserted {
            let project = try decoder.decode(
                DocumentProject.self,
                from: Data(contentsOf: snapshotsRoot(previousRoot)
                    .appendingPathComponent("\(item.documentID).json"))
            )
            let suffix = ".\(item.format.fileExtension)"
            guard item.destinationFile.hasSuffix(suffix) else {
                throw BatchExportError.invalidFileStem(item.destinationFile)
            }
            let stem = String(item.destinationFile.dropLast(suffix.count))
            documents.append(BatchDocumentInput(project: project, fileStem: stem))
        }
        return BatchExportRequest(
            operationID: newOperationID,
            retryOfOperationID: previousOperationID,
            destination: destination,
            documents: documents,
            formats: manifest.selectedFormats,
            flatteningConsent: []
        )
    }

    func operationExists(destination: URL, operationID: String) -> Bool {
        fileManager.fileExists(atPath: operationRoot(
            for: destination,
            operationID: operationID
        ).path)
    }

    func recover(destination: URL, operationID: String) throws -> BatchExportManifest {
        let root = operationRoot(for: destination, operationID: operationID)
        return try recover(operationRoot: root, destination: destination)
    }

    private func recover(
        operationRoot root: URL,
        destination: URL
    ) throws -> BatchExportManifest {
        var manifest = try decoder.decode(
            BatchExportManifest.self,
            from: Data(contentsOf: manifestURL(root))
        )
        var interrupted = false
        var recoveredItems: [BatchExportItem] = []
        for item in manifest.items {
            if [.published, .failed, .cancelled].contains(item.state) {
                recoveredItems.append(item)
                continue
            }
            switch try reconcilePublication(
                item,
                manifestSchemaVersion: manifest.schemaVersion,
                destination: destination
            ) {
            case .published(let published):
                recoveredItems.append(published)
            case .failed(let code, let message):
                interrupted = true
                recoveredItems.append(item.updating(
                    state: .failed,
                    progressCompleted: item.progressCompleted,
                    diagnosticCode: code,
                    diagnosticMessage: message
                ))
            }
        }
        try cleanupStaging(root)
        let recoveredState: BatchOperationState
        if interrupted {
            recoveredState = .interrupted
        } else if recoveredItems.contains(where: { $0.state == .failed }) {
            recoveredState = .completedWithErrors
        } else if recoveredItems.contains(where: { $0.state == .cancelled }) {
            recoveredState = .cancelled
        } else {
            recoveredState = .completed
        }
        manifest = manifest.updating(
            state: recoveredState,
            cleanupState: .clean,
            items: recoveredItems
        )
        try persist(manifest, at: root)
        return manifest
    }

    func recoverInterrupted(destination: URL) throws -> [BatchExportManifest] {
        let stateRoot = destination.appendingPathComponent(Self.stateDirectoryName, isDirectory: true)
        guard fileManager.fileExists(atPath: stateRoot.path) else { return [] }
        let operations = try fileManager.contentsOfDirectory(
            at: stateRoot,
            includingPropertiesForKeys: nil,
            options: [.skipsHiddenFiles]
        )
        var recovered: [BatchExportManifest] = []
        for operation in operations.sorted(by: { $0.lastPathComponent < $1.lastPathComponent }) {
            let values = try operation.resourceValues(forKeys: [
                .isDirectoryKey,
                .isSymbolicLinkKey,
            ])
            guard values.isDirectory == true, values.isSymbolicLink != true else { continue }
            guard fileManager.fileExists(atPath: manifestURL(operation).path) else {
                try cleanupStaging(operation)
                continue
            }
            let manifest = try decoder.decode(
                BatchExportManifest.self,
                from: Data(contentsOf: manifestURL(operation))
            )
            if manifest.state == .running || manifest.cleanupState == .pending {
                recovered.append(try recover(operationRoot: operation, destination: destination))
            }
        }
        return recovered
    }

    func persist(_ manifest: BatchExportManifest, at operationRoot: URL) throws {
        try encoder.encode(manifest).write(to: manifestURL(operationRoot), options: .atomic)
    }

    func cleanupItem(_ operationRoot: URL, itemID: String) throws {
        let root = itemStagingRoot(operationRoot, itemID: itemID)
        if fileManager.fileExists(atPath: root.path) { try fileManager.removeItem(at: root) }
    }

    func cleanupStaging(_ operationRoot: URL) throws {
        let root = stagingRoot(operationRoot)
        if fileManager.fileExists(atPath: root.path) { try fileManager.removeItem(at: root) }
    }

    func operationRoot(for destination: URL, operationID: String) -> URL {
        destination.appendingPathComponent(Self.stateDirectoryName, isDirectory: true)
            .appendingPathComponent(operationID, isDirectory: true)
    }

    func itemStagingRoot(_ operationRoot: URL, itemID: String) -> URL {
        stagingRoot(operationRoot).appendingPathComponent(itemID, isDirectory: true)
    }

    private func snapshotsRoot(_ operationRoot: URL) -> URL {
        operationRoot.appendingPathComponent("snapshots", isDirectory: true)
    }

    private func stagingRoot(_ operationRoot: URL) -> URL {
        operationRoot.appendingPathComponent("staging", isDirectory: true)
    }

    private func manifestURL(_ operationRoot: URL) -> URL {
        operationRoot.appendingPathComponent("manifest.json")
    }

    private enum PublicationReconciliation {
        case published(BatchExportItem)
        case failed(code: String, message: String)
    }

    private func reconcilePublication(
        _ item: BatchExportItem,
        manifestSchemaVersion: Int,
        destination: URL
    ) throws -> PublicationReconciliation {
        guard item.state == .validated else {
            return .failed(
                code: "interrupted-before-publication",
                message: "게시 전 중단 상태를 복구했습니다."
            )
        }
        let intent: BatchPublicationIntent?
        if let publicationIntent = item.publicationIntent {
            intent = publicationIntent
        } else if manifestSchemaVersion == 1, let artifactHash = item.artifactHash {
            intent = BatchPublicationIntent(
                destinationFile: item.destinationFile,
                expectedArtifactHash: artifactHash
            )
        } else {
            intent = nil
        }
        guard let intent,
              intent.destinationFile == item.destinationFile,
              intent.expectedArtifactHash == item.artifactHash
        else {
            return .failed(
                code: "publication-intent-invalid",
                message: "게시 의도 또는 예상 해시가 유효하지 않습니다."
            )
        }
        guard let artifact = confinedDestinationURL(
            destinationFile: intent.destinationFile,
            destination: destination
        ) else {
            return .failed(
                code: "publication-path-invalid",
                message: "게시 대상 경로가 내보내기 폴더를 벗어납니다."
            )
        }
        guard let actualHash = try regularFileHash(at: artifact) else {
            return .failed(
                code: "publication-artifact-missing",
                message: "게시 대상의 일반 파일을 찾을 수 없습니다."
            )
        }
        guard actualHash == intent.expectedArtifactHash else {
            return .failed(
                code: "publication-artifact-hash-mismatch",
                message: "게시 대상 해시가 검증된 산출물과 일치하지 않습니다."
            )
        }
        return .published(item.updating(
            state: .published,
            progressCompleted: Self.progressTotal,
            artifactHash: actualHash,
            publicationIntent: intent,
            diagnosticCode: "reconciled-after-publication-move",
            diagnosticMessage: "이동 완료 산출물을 예상 해시로 복구했습니다."
        ))
    }

    private func confinedDestinationURL(
        destinationFile: String,
        destination: URL
    ) -> URL? {
        guard !destinationFile.isEmpty,
              destinationFile != ".",
              destinationFile != "..",
              !destinationFile.contains("/"),
              URL(fileURLWithPath: destinationFile).lastPathComponent == destinationFile
        else { return nil }
        let root = destination.standardizedFileURL.resolvingSymlinksInPath()
        let candidate = destination.appendingPathComponent(
            destinationFile,
            isDirectory: false
        ).standardizedFileURL
        let parent = candidate.deletingLastPathComponent().resolvingSymlinksInPath()
        guard parent.path == root.path else { return nil }
        return candidate
    }

    private func regularFileHash(at url: URL) throws -> String? {
        let descriptor = url.path.withCString {
            Darwin.open($0, O_RDONLY | O_NOFOLLOW)
        }
        guard descriptor >= 0 else { return nil }
        defer { Darwin.close(descriptor) }
        var opened = stat()
        guard fstat(descriptor, &opened) == 0,
              opened.st_mode & S_IFMT == S_IFREG
        else { return nil }
        let handle = FileHandle(fileDescriptor: descriptor, closeOnDealloc: false)
        var digest = SHA256()
        while let chunk = try handle.read(upToCount: 1_048_576), !chunk.isEmpty {
            digest.update(data: chunk)
        }
        var current = stat()
        let stillSameFile = url.path.withCString {
            lstat($0, &current) == 0
                && current.st_mode & S_IFMT == S_IFREG
                && current.st_dev == opened.st_dev
                && current.st_ino == opened.st_ino
        }
        guard stillSameFile else { return nil }
        return "sha256:" + digest.finalize().map { String(format: "%02x", $0) }.joined()
    }
}
