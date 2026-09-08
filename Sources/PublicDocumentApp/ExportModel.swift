import Foundation

enum DocumentFormat: String, Codable, CaseIterable {
    case hwpx
    case hwp
    case docx
    case markdown

    var fileExtension: String {
        switch self {
        case .hwpx: return "hwpx"
        case .hwp: return "hwp"
        case .docx: return "docx"
        case .markdown: return "md"
        }
    }
}

enum LossClassification: String, Codable {
    case visualOnlyFlattening = "visual-only-flattening"
    case semanticLoss = "semantic-loss"
}

enum ExportEvidenceSource: String, Codable {
    case preflightPolicy = "preflight-policy"
    case artifactDerived = "artifact-derived"
}

struct LossReport: Codable, Equatable {
    let format: DocumentFormat
    let capability: String
    let elementID: String
    let elementPath: String
    let classification: LossClassification
    let fallback: String
    let requiresConsent: Bool
    let evidenceSource: ExportEvidenceSource
}

struct ExportCapabilityObservation: Codable, Equatable, Hashable {
    let capability: String
    let elementID: String
    let elementPath: String
}

struct ExportResult: Codable {
    let format: DocumentFormat
    let fileName: String
    let relativePath: String
    let artifactHash: String
    let byteCount: Int
    let structuralValid: Bool
    let semanticValid: Bool
    let validator: String
    let validation: FormatValidationReceipt
    let engineIdentity: ExportEngineIdentity?
}

struct ExportEngineIdentity: Codable {
    let engine: String
    let packageName: String
    let upstreamCommit: String
    let nodeVersion: String
    let nodeArchitecture: String
    let nodeSHA256: String
    let cliSHA256: String
    let savedAt: String
}

enum ExportFailureStage: String, Codable {
    case adapter
    case validation
    case destination
}

struct ExportFailureDisposition: Codable {
    let format: DocumentFormat
    let stage: ExportFailureStage
    let errorCode: String
    let userDiagnostic: String

    init(format: DocumentFormat, stage: ExportFailureStage, error: Error) {
        self.format = format
        self.stage = stage
        if let exportError = error as? ExportError {
            errorCode = exportError.diagnosticCode
            userDiagnostic = exportError.errorDescription ?? exportError.localizedDescription
        } else {
            errorCode = "\(stage.rawValue)-failed"
            userDiagnostic = error.localizedDescription
        }
    }
}

struct TypstSidecarReceipt: Codable {
    let state: String
    let sourceFile: String?
    let pdfFile: String?
    let diagnosticCode: String
    var diagnosticMessage: String? = nil
}

struct ExportReceipt: Codable {
    let operationID: String
    let snapshotRevisionID: String
    let snapshotHash: String
    let fixtureHash: String
    let selectedFormats: [DocumentFormat]
    let publishedFormats: [DocumentFormat]
    let blockedFormats: [DocumentFormat]
    let failedFormats: [DocumentFormat]
    let failures: [ExportFailureDisposition]
    let results: [ExportResult]
    let lossReports: [LossReport]
    let observedCapabilities: [ExportCapabilityObservation]
    let observedFrozenCombinations: [String]
    let flatteningConsentRecorded: Bool
    let flatteningConsentFormats: [DocumentFormat]
    let allAuthoredElementIDsPreserved: Bool
    let rhwpCommit: String
    let sidecar: TypstSidecarReceipt?
}

struct ExportRequest {
    let operationID: String
    let destination: URL
    let formats: [DocumentFormat]
    let flatteningConsent: Set<DocumentFormat>
}

enum ExportError: Error, LocalizedError {
    case noFormatSelected
    case destinationExists(String)
    case invalidPackage(String)
    case missingRhwpEngine
    case rhwpFailed(String)
    case missingGenOfficeDocxEngine
    case genOfficeDocxFailed(String)
    case unsupportedElementKind(String)

    var diagnosticCode: String {
        switch self {
        case .noFormatSelected: return "no-format-selected"
        case .destinationExists: return "destination-exists"
        case .invalidPackage: return "invalid-package"
        case .missingRhwpEngine: return "missing-rhwp-engine"
        case .rhwpFailed: return "rhwp-failed"
        case .missingGenOfficeDocxEngine: return "missing-genoffice-docx-engine"
        case .genOfficeDocxFailed: return "genoffice-docx-failed"
        case .unsupportedElementKind: return "unsupported-element-kind"
        }
    }

    var errorDescription: String? {
        switch self {
        case .noFormatSelected:
            return "내보낼 형식을 하나 이상 선택하세요."
        case .destinationExists(let name):
            return "기존 파일은 자동으로 덮어쓰지 않습니다: \(name)"
        case .invalidPackage(let detail):
            return "내보낸 패키지 검증에 실패했습니다: \(detail)"
        case .missingRhwpEngine:
            return "고정된 rhwp 내보내기 엔진을 찾을 수 없습니다."
        case .rhwpFailed(let detail):
            return "rhwp HWP 변환 또는 자기 재열기 검증에 실패했습니다: \(detail)"
        case .missingGenOfficeDocxEngine:
            return "고정된 GenOffice DOCX 정규화 엔진을 찾을 수 없거나 무결성 검증에 실패했습니다."
        case .genOfficeDocxFailed(let detail):
            return "GenOffice DOCX 정규화에 실패했습니다: \(detail)"
        case .unsupportedElementKind(let kind):
            return "고정 작성 기능 목록에 없는 요소입니다: \(kind)"
        }
    }
}

enum ExportCapabilities {
    static let manifestVersion = "1.0.0"
    static let rhwpCommit = "2dced7bfe10c6597cead634264c7c1781c01f1e7"
    static let authorableKinds: Set<String> = [
        "metadata", "heading", "paragraph", "table", "review-marker", "approval-grid", "formula",
        "list-item",
    ]

    static func lossReports(
        project: DocumentProject,
        format: DocumentFormat
    ) throws -> [LossReport] {
        try FormatCapabilityPolicy.lossReports(project: project, format: format)
    }
}
