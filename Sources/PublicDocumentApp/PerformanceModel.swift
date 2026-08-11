import Foundation

struct PerformanceFixtureRequirement: Codable {
    let minimumPageCount: Int?
    let minimumSnapshotBytes: Int?
    let minimumAuthoredUTF8Bytes: Int?
    let elementChunkBytes: Int?
    let elementCount: Int?
}

struct PerformanceThresholds: Codable {
    let exportSeconds: Double
    let mainThreadHeartbeatMilliseconds: Double
    let firstProgressMilliseconds: Double
    let progressGapMilliseconds: Double
    let cancellationRequestMilliseconds: Double
    let cancellationCompletionMilliseconds: Double
}

struct PerformanceProfile: Codable {
    let profileVersion: String
    let requiredArchitecture: String
    let fixtures: [String: PerformanceFixtureRequirement]
    let formats: [DocumentFormat]
    let thresholds: PerformanceThresholds
}

struct PerformanceEnvironment: Codable {
    let modelIdentifier: String
    let processor: String
    let architecture: String
    let physicalMemoryBytes: UInt64
    let osVersion: String
    let osBuild: String
    let applicationVersion: String
    let recordedAt: String
}

struct PerformanceFixtureObservation: Codable {
    let fixtureID: String
    let declaredPageCount: Int?
    let snapshotByteCount: Int
    let snapshotHash: String
    let authoredElementCount: Int
    let authoredUTF8ByteCount: Int
    let authoredContentHash: String
    let snapshotThresholdPassed: Bool
    let authoredUTF8ThresholdPassed: Bool
}

struct PerformanceExportObservation: Codable {
    let operationID: String
    let fixtureID: String
    let format: DocumentFormat
    let snapshotHash: String
    let durationSeconds: Double
    let renderedPageCount: Int?
    let artifactRelativePath: String
    let artifactHash: String
    let artifactByteCount: Int
    let authoredUTF8ByteCount: Int
    let authoredContentHash: String
    let authoredContentValidator: String
    let authoredContentValidated: Bool
    let structuralValid: Bool
    let semanticValid: Bool
    let validator: String
    let passed: Bool
}

struct PerformanceInteractionObservation: Codable {
    let heartbeatCount: Int
    let maximumHeartbeatGapMilliseconds: Double
    let firstProgressMilliseconds: Double
    let maximumProgressGapMilliseconds: Double
    let progressEventCount: Int
    let cancellationRequestMilliseconds: Double
    let cancellationCompletionMilliseconds: Double
    let responsive: Bool
    let progressPassed: Bool
    let cancellationPassed: Bool
}

struct PerformanceReceipt: Codable {
    let profileVersion: String
    let profileHash: String
    let environment: PerformanceEnvironment
    let fixtures: [PerformanceFixtureObservation]
    let exportObservations: [PerformanceExportObservation]
    let interactionObservation: PerformanceInteractionObservation
    let overallVerdict: String
}

struct PerformanceAuthoredPayload: Equatable {
    let elementCount: Int
    let utf8ByteCount: Int
    let contentHash: String
}

struct PerformanceAuthoredContentValidation {
    let payload: PerformanceAuthoredPayload
    let validator: String
    let valid: Bool
}

final class PerformanceExportOutcomeBox {
    private let lock = NSLock()
    private var receipt: ExportReceipt?
    private var failure: Error?

    func finish(_ result: Result<ExportReceipt, Error>) {
        lock.lock()
        switch result {
        case .success(let value): receipt = value
        case .failure(let error): failure = error
        }
        lock.unlock()
    }

    func value() throws -> ExportReceipt {
        lock.lock()
        defer { lock.unlock() }
        if let failure { throw failure }
        guard let receipt else { throw ExportError.invalidPackage("성능 시험 결과가 없습니다") }
        return receipt
    }
}

struct MeasuredExport {
    let receipt: ExportReceipt
    let durationSeconds: Double
    let heartbeatCount: Int
    let maximumHeartbeatGapMilliseconds: Double
}

struct RhwpPageInfo: Decodable {
    let pageCount: Int
}
