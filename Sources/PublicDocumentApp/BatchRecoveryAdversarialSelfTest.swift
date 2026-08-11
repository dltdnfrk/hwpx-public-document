import CryptoKit
import Foundation

struct BatchRecoveryAdversarialEvidence {
    let hashMismatch: BatchExportManifest
    let nonRegular: BatchExportManifest
    let pathEscape: BatchExportManifest
    let legacyV1: BatchExportManifest
}

enum BatchRecoveryAdversarialSelfTest {
    static func run(
        root: URL,
        coordinator: BatchExportCoordinator,
        fixture: BatchDocumentInput
    ) throws -> BatchRecoveryAdversarialEvidence {
        BatchRecoveryAdversarialEvidence(
            hashMismatch: try hashMismatch(root: root, coordinator: coordinator, fixture: fixture),
            nonRegular: try nonRegular(root: root, coordinator: coordinator, fixture: fixture),
            pathEscape: try syntheticRecovery(
                root: root,
                coordinator: coordinator,
                fixture: fixture,
                operationID: "batch-ac06-path-escape",
                schemaVersion: 2,
                destinationFile: "../ac06-outside.docx",
                includesCurrentFields: true
            ),
            legacyV1: try syntheticRecovery(
                root: root,
                coordinator: coordinator,
                fixture: fixture,
                operationID: "batch-ac06-legacy-v1",
                schemaVersion: 1,
                destinationFile: "legacy-missing.docx",
                includesCurrentFields: false
            )
        )
    }

    private static func hashMismatch(
        root: URL,
        coordinator: BatchExportCoordinator,
        fixture: BatchDocumentInput
    ) throws -> BatchExportManifest {
        let operationID = "batch-ac06-hash-mismatch"
        let destinationFile = "생활안전-해시불일치.docx"
        try crashAfterMove(
            root: root,
            coordinator: coordinator,
            fixture: fixture,
            operationID: operationID,
            fileStem: "생활안전-해시불일치"
        )
        try Data("ac06-hash-mismatch".utf8).write(
            to: root.appendingPathComponent(destinationFile),
            options: .atomic
        )
        return try coordinator.recover(destination: root, operationID: operationID)
    }

    private static func nonRegular(
        root: URL,
        coordinator: BatchExportCoordinator,
        fixture: BatchDocumentInput
    ) throws -> BatchExportManifest {
        let operationID = "batch-ac06-non-regular"
        let artifact = root.appendingPathComponent("생활안전-심볼릭.docx")
        try crashAfterMove(
            root: root,
            coordinator: coordinator,
            fixture: fixture,
            operationID: operationID,
            fileStem: "생활안전-심볼릭"
        )
        let target = root.appendingPathComponent("ac06-symlink-target")
        try Data("not-the-validated-artifact".utf8).write(to: target, options: .atomic)
        try FileManager.default.removeItem(at: artifact)
        try FileManager.default.createSymbolicLink(at: artifact, withDestinationURL: target)
        return try coordinator.recover(destination: root, operationID: operationID)
    }

    private static func crashAfterMove(
        root: URL,
        coordinator: BatchExportCoordinator,
        fixture: BatchDocumentInput,
        operationID: String,
        fileStem: String
    ) throws {
        do {
            _ = try coordinator.run(
                request: BatchExportRequest(
                    operationID: operationID,
                    retryOfOperationID: nil,
                    destination: root,
                    documents: [BatchDocumentInput(project: fixture.project, fileStem: fileStem)],
                    formats: [.docx],
                    flatteningConsent: [.docx]
                ),
                execution: BatchExportExecution(
                    fault: .crashAfterPublicationMove,
                    cancelAfterPublishedCount: nil
                )
            )
        } catch BatchExportError.simulatedCrash {
            return
        }
        throw ExportError.invalidPackage("게시 이동 뒤 시험용 비정상 종료가 발생하지 않았습니다.")
    }

    private static func syntheticRecovery(
        root: URL,
        coordinator: BatchExportCoordinator,
        fixture: BatchDocumentInput,
        operationID: String,
        schemaVersion: Int,
        destinationFile: String,
        includesCurrentFields: Bool
    ) throws -> BatchExportManifest {
        let operationRoot = root
            .appendingPathComponent(".public-document-studio-exports", isDirectory: true)
            .appendingPathComponent(operationID, isDirectory: true)
        try FileManager.default.createDirectory(
            at: operationRoot.appendingPathComponent("staging", isDirectory: true),
            withIntermediateDirectories: true
        )
        let expectedHash = "sha256:" + SHA256.hash(data: Data(operationID.utf8))
            .map { String(format: "%02x", $0) }.joined()
        let item = BatchExportItem(
            itemID: "\(operationID)-docx",
            documentID: fixture.project.documentID,
            documentDisplayName: includesCurrentFields ? fixture.project.title : nil,
            snapshotRevisionID: fixture.project.currentRevisionID,
            snapshotHash: expectedHash,
            format: .docx,
            destinationFile: destinationFile,
            state: .validated,
            progressCompleted: 3,
            progressTotal: 4,
            artifactHash: expectedHash,
            publicationIntent: includesCurrentFields ? BatchPublicationIntent(
                destinationFile: destinationFile,
                expectedArtifactHash: expectedHash
            ) : nil,
            diagnosticCode: "",
            diagnosticMessage: ""
        )
        let manifestPath = operationRoot.appendingPathComponent("manifest.json")
        let manifest = BatchExportManifest(
            schemaVersion: schemaVersion,
            operationID: operationID,
            retryOfOperationID: nil,
            state: .running,
            cleanupState: .pending,
            manifestPath: manifestPath.path,
            selectedFormats: [.docx],
            flatteningConsent: [],
            items: [item]
        )
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        try encoder.encode(manifest).write(to: manifestPath, options: .atomic)
        return try coordinator.recover(destination: root, operationID: operationID)
    }
}
