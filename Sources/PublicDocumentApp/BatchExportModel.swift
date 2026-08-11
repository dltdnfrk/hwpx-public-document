import Foundation

enum BatchItemState: String, Codable {
    case queued
    case exporting
    case validated
    case published
    case failed
    case cancelled
}

enum BatchOperationState: String, Codable {
    case running
    case completed
    case completedWithErrors = "completed-with-errors"
    case cancelled
    case interrupted
}

enum BatchCleanupState: String, Codable {
    case pending
    case clean
}

struct BatchExportItem: Codable {
    let itemID: String
    let documentID: String
    let documentDisplayName: String?
    let snapshotRevisionID: String
    let snapshotHash: String
    let format: DocumentFormat
    let destinationFile: String
    let state: BatchItemState
    let progressCompleted: Int
    let progressTotal: Int
    let artifactHash: String?
    let publicationIntent: BatchPublicationIntent?
    let diagnosticCode: String
    let diagnosticMessage: String

    func updating(
        state: BatchItemState,
        progressCompleted: Int,
        artifactHash: String? = nil,
        publicationIntent: BatchPublicationIntent? = nil,
        diagnosticCode: String = "",
        diagnosticMessage: String = ""
    ) -> BatchExportItem {
        BatchExportItem(
            itemID: itemID,
            documentID: documentID,
            documentDisplayName: documentDisplayName,
            snapshotRevisionID: snapshotRevisionID,
            snapshotHash: snapshotHash,
            format: format,
            destinationFile: destinationFile,
            state: state,
            progressCompleted: progressCompleted,
            progressTotal: progressTotal,
            artifactHash: artifactHash ?? self.artifactHash,
            publicationIntent: publicationIntent ?? self.publicationIntent,
            diagnosticCode: diagnosticCode,
            diagnosticMessage: diagnosticMessage
        )
    }
}

struct BatchPublicationIntent: Codable {
    let destinationFile: String
    let expectedArtifactHash: String
}

struct BatchDestinationIntegrity: Codable {
    let destinationFile: String
    let beforeByteCount: Int
    let afterByteCount: Int
    let beforeSHA256: String
    let afterSHA256: String
    let existingBytesPreserved: Bool
}

struct BatchExportManifest: Codable {
    let schemaVersion: Int
    let operationID: String
    let retryOfOperationID: String?
    let state: BatchOperationState
    let cleanupState: BatchCleanupState
    let manifestPath: String
    let selectedFormats: [DocumentFormat]
    let flatteningConsent: [DocumentFormat]?
    var destinationIntegrity: BatchDestinationIntegrity? = nil
    let items: [BatchExportItem]

    func updating(
        state: BatchOperationState? = nil,
        cleanupState: BatchCleanupState? = nil,
        items: [BatchExportItem]? = nil
    ) -> BatchExportManifest {
        var updated = BatchExportManifest(
            schemaVersion: schemaVersion,
            operationID: operationID,
            retryOfOperationID: retryOfOperationID,
            state: state ?? self.state,
            cleanupState: cleanupState ?? self.cleanupState,
            manifestPath: manifestPath,
            selectedFormats: selectedFormats,
            flatteningConsent: flatteningConsent,
            items: items ?? self.items
        )
        updated.destinationIntegrity = destinationIntegrity
        return updated
    }
}

struct BatchDocumentInput {
    let project: DocumentProject
    let fileStem: String
}

struct BatchExportRequest {
    let operationID: String
    let retryOfOperationID: String?
    let destination: URL
    let documents: [BatchDocumentInput]
    let formats: [DocumentFormat]
    let flatteningConsent: Set<DocumentFormat>
}

enum BatchExportFault {
    case none
    case processFailure(documentID: String, format: DocumentFormat)
    case crashBeforeInitialManifest
    case crashBeforePublication
    case crashAfterPublicationMove
    case diskFullBeforePublication
}

struct BatchExportExecution {
    let fault: BatchExportFault
    let cancelAfterPublishedCount: Int?

    static let normal = BatchExportExecution(fault: .none, cancelAfterPublishedCount: nil)
}

final class BatchExportCancellation {
    private let lock = NSLock()
    private var cancelled = false

    func cancel() {
        lock.lock()
        cancelled = true
        lock.unlock()
    }

    func isCancelled() -> Bool {
        lock.lock()
        defer { lock.unlock() }
        return cancelled
    }
}

enum BatchExportError: Error, LocalizedError {
    case duplicateOperation(String)
    case invalidFileStem(String)
    case missingSnapshot(String)
    case injectedProcessFailure
    case simulatedCrash
    case simulatedDiskFull

    var errorDescription: String? {
        switch self {
        case .duplicateOperation(let operationID):
            return "이미 존재하는 작업 ID입니다: \(operationID)"
        case .invalidFileStem(let fileStem):
            return "안전하지 않은 내보내기 파일 이름입니다: \(fileStem)"
        case .missingSnapshot(let documentID):
            return "배치 스냅샷 문서를 찾을 수 없습니다: \(documentID)"
        case .injectedProcessFailure:
            return "시험용 하위 프로세스 실패"
        case .simulatedCrash:
            return "시험용 게시 전 비정상 종료"
        case .simulatedDiskFull:
            return "시험용 게시 전 디스크 공간 부족"
        }
    }
}
