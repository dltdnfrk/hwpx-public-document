import CryptoKit
import Foundation

enum BatchExportSelfTestScenario: String {
    case partialFailure = "partial-failure"
    case cancelAfterFirst = "cancel-after-first"
    case cancelBeforePublication = "cancel-before-publication"
    case existingDestination = "existing-destination"
    case crashAndRetry = "crash-and-retry"
    case diskFullAndRetry = "disk-full-and-retry"
}

struct BatchRecoverySelfTestReceipt: Codable {
    let root: String
    let recovered: BatchExportManifest
    let retry: BatchExportManifest
    let reconciledAfterMove: BatchExportManifest?
    let hashMismatchRecovered: BatchExportManifest?
    let nonRegularRecovered: BatchExportManifest?
    let pathEscapeRecovered: BatchExportManifest?
    let legacyV1Recovered: BatchExportManifest?
    let startupRecovered: [BatchExportManifest]?
    let manifestlessOperationID: String?
    let manifestlessOperationExists: Bool?
    let manifestlessManifestExists: Bool?
}

enum BatchExportSelfTest {
    static func run(
        at root: URL,
        scenario: BatchExportSelfTestScenario
    ) throws -> BatchExportManifest {
        let coordinator = BatchExportCoordinator()
        switch scenario {
        case .partialFailure:
            return try coordinator.run(
                request: request(
                    operationID: "batch-ac06-partial",
                    root: root,
                    documents: fixtures(),
                    formats: [.docx, .markdown]
                ),
                execution: BatchExportExecution(
                    fault: .processFailure(documentID: "document-ac06-b", format: .docx),
                    cancelAfterPublishedCount: nil
                )
            )
        case .cancelAfterFirst:
            return try coordinator.run(
                request: request(
                    operationID: "batch-ac06-cancelled",
                    root: root,
                    documents: fixtures(),
                    formats: [.docx, .markdown]
                ),
                execution: BatchExportExecution(fault: .none, cancelAfterPublishedCount: 1)
            )
        case .cancelBeforePublication:
            let cancellation = BatchExportCancellation()
            return try coordinator.run(
                request: request(
                    operationID: "batch-ac06-cancel-before-publication",
                    root: root,
                    documents: [fixtures()[0]],
                    formats: [.docx]
                ),
                cancellation: cancellation
            ) { manifest in
                if manifest.items.first?.state == .validated { cancellation.cancel() }
            }
        case .existingDestination:
            let existing = root.appendingPathComponent("생활안전-계획.docx")
            let before = try Data(contentsOf: existing)
            let manifest = try coordinator.run(request: request(
                operationID: "batch-ac06-existing",
                root: root,
                documents: [fixtures()[0]],
                formats: [.docx, .markdown]
            ))
            if ProcessInfo.processInfo.environment[
                "PUBLIC_DOCUMENT_AC06_TEST_MUTATE_EXISTING_DESTINATION"
            ] == "1" {
                try Data("ac06-integrity-regression".utf8).write(to: existing, options: .atomic)
            }
            let after = try Data(contentsOf: existing)
            var attested = manifest
            attested.destinationIntegrity = BatchDestinationIntegrity(
                destinationFile: existing.lastPathComponent,
                beforeByteCount: before.count,
                afterByteCount: after.count,
                beforeSHA256: "sha256:" + SHA256.hash(data: before)
                    .map { String(format: "%02x", $0) }.joined(),
                afterSHA256: "sha256:" + SHA256.hash(data: after)
                    .map { String(format: "%02x", $0) }.joined(),
                existingBytesPreserved: before == after
            )
            let encoder = JSONEncoder()
            encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
            try encoder.encode(attested).write(
                to: URL(fileURLWithPath: attested.manifestPath),
                options: .atomic
            )
            return attested
        case .crashAndRetry, .diskFullAndRetry:
            throw ExportError.invalidPackage("복구 자체 시험에는 runRecovery를 사용해야 합니다.")
        }
    }

    static func runRecovery(
        at root: URL,
        scenario: BatchExportSelfTestScenario
    ) throws -> BatchRecoverySelfTestReceipt {
        let coordinator = BatchExportCoordinator()
        switch scenario {
        case .crashAndRetry:
            let previousID = "batch-ac06-crashed"
            let retryID = "batch-ac06-retry-after-crash"
            let documents = [fixtures()[0]]
            try expectCrash {
                _ = try coordinator.run(
                    request: request(
                        operationID: previousID,
                        root: root,
                        documents: documents,
                        formats: [.docx]
                    ),
                    execution: BatchExportExecution(
                        fault: .crashBeforePublication,
                        cancelAfterPublishedCount: nil
                    )
                )
            }
            let recovered = try coordinator.recover(
                destination: root,
                operationID: previousID
            )
            let retry = try coordinator.retry(
                destination: root,
                previousOperationID: previousID,
                newOperationID: retryID
            )
            let reconciled = try crashAfterMoveRecovery(
                root: root,
                coordinator: coordinator
            )
            let startup = try startupRecovery(
                root: root,
                coordinator: coordinator
            )
            let adversarial = try BatchRecoveryAdversarialSelfTest.run(
                root: root,
                coordinator: coordinator,
                fixture: documents[0]
            )
            let manifestlessID = "batch-ac06-pre-manifest"
            let manifestlessManifest = root
                .appendingPathComponent(".public-document-studio-exports", isDirectory: true)
                .appendingPathComponent(manifestlessID, isDirectory: true)
                .appendingPathComponent("manifest.json")
            return BatchRecoverySelfTestReceipt(
                root: root.path,
                recovered: recovered,
                retry: retry,
                reconciledAfterMove: reconciled,
                hashMismatchRecovered: adversarial.hashMismatch,
                nonRegularRecovered: adversarial.nonRegular,
                pathEscapeRecovered: adversarial.pathEscape,
                legacyV1Recovered: adversarial.legacyV1,
                startupRecovered: startup,
                manifestlessOperationID: manifestlessID,
                manifestlessOperationExists: coordinator.operationExists(
                    destination: root,
                    operationID: manifestlessID
                ),
                manifestlessManifestExists: FileManager.default.fileExists(
                    atPath: manifestlessManifest.path
                )
            )
        case .diskFullAndRetry:
            let previousID = "batch-ac06-disk-full"
            let recovered = try coordinator.run(
                request: request(
                    operationID: previousID,
                    root: root,
                    documents: [fixtures()[0]],
                    formats: [.docx]
                ),
                execution: BatchExportExecution(
                    fault: .diskFullBeforePublication,
                    cancelAfterPublishedCount: nil
                )
            )
            let retry = try coordinator.retry(
                destination: root,
                previousOperationID: previousID,
                newOperationID: "batch-ac06-retry-after-disk-full"
            )
            return BatchRecoverySelfTestReceipt(
                root: root.path,
                recovered: recovered,
                retry: retry,
                reconciledAfterMove: nil,
                hashMismatchRecovered: nil,
                nonRegularRecovered: nil,
                pathEscapeRecovered: nil,
                legacyV1Recovered: nil,
                startupRecovered: nil,
                manifestlessOperationID: nil,
                manifestlessOperationExists: nil,
                manifestlessManifestExists: nil
            )
        case .partialFailure, .cancelAfterFirst, .cancelBeforePublication, .existingDestination:
            throw ExportError.invalidPackage("일반 배치 자체 시험에는 run을 사용해야 합니다.")
        }
    }
}
