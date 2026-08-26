import CryptoKit
import Darwin
import Foundation

extension BatchExportStore {
    func recover(destination: URL, operationID: String) throws -> BatchExportManifest {
        let root = operationRoot(for: destination, operationID: operationID)
        return try recover(operationRoot: root, destination: destination)
    }

    func recover(
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
