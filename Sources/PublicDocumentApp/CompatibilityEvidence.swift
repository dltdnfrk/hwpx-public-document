import Foundation

enum CompatibilityVerdict: String, Codable {
    case pass
    case fail
    case blocked
}

struct CompatibilityArtifact: Codable {
    let fixtureID: String
    let fixtureHash: String
    let format: DocumentFormat
    let relativePath: String
    let artifactHash: String
    let byteCount: Int
    let validation: CompatibilityArtifactValidation?
}

struct CompatibilityValidatedElement: Codable, Equatable {
    let elementID: String
    let kind: String
    let order: Int
    let textHash: String
}

struct CompatibilityArtifactValidation: Codable {
    let structuralValid: Bool
    let semanticValid: Bool
    let evidenceSource: String
    let validator: String
    let orderedElements: [CompatibilityValidatedElement]
}

enum CompatibilityDisposition: String, Codable {
    case artifactValidated = "artifact-validated"
    case semanticLossBlocked = "semantic-loss-blocked"
}

struct CompatibilityFormatDisposition: Codable {
    let fixtureID: String
    let fixtureHash: String
    let format: DocumentFormat
    let disposition: CompatibilityDisposition
    let capabilityGaps: [String]
}

struct CompatibilityObservation: Codable {
    let observationID: String
    let clientID: String
    let clientName: String
    let clientVersion: String
    let clientBuild: String
    let osVersion: String
    let osBuild: String
    let fonts: [String]
    let timestamp: String
    let fixtureID: String
    let fixtureHash: String
    let format: DocumentFormat
    let artifactHash: String
    let operation: String
    let opened: Bool?
    let extensionWarningCount: Int?
    let expectedTextCount: Int?
    let observedTextCount: Int?
    let expectedPageCount: Int?
    let observedPageCount: Int?
    let unexpectedBlankPageCount: Int?
    let evidencePath: String?
    let evidenceHash: String?
    let diagnostics: String?
    let verdict: CompatibilityVerdict?
}

struct CompatibilityVisualObservation: Codable {
    let observationID: String
    let toolID: String
    let clientName: String
    let clientVersion: String
    let clientBuild: String
    let osVersion: String
    let osBuild: String
    let fonts: [String]
    let timestamp: String
    let fixtureID: String
    let fixtureHash: String
    let format: DocumentFormat
    let artifactHash: String
    let expectedPageCount: Int?
    let observedPageCount: Int?
    let missingAuthoredElementIDs: [String]?
    let unexpectedBlankPageNumbers: [Int]?
    let textBoundsCoverage: Double?
    let evidencePath: String?
    let evidenceHash: String?
}

enum CompatibilityVerdictClass: String, Codable {
    case visual
    case client
}

enum CompatibilityExternalBlockerStatus: String, Codable {
    case blocked = "BLOCKED"
}

struct CompatibilityEvidenceReference: Codable, Equatable {
    let path: String
    let sha256: String
}

struct CompatibilityExternalBlocker: Codable {
    let blockerID: String
    let verdictClass: CompatibilityVerdictClass
    let fixtureID: String
    let fixtureHash: String
    let format: DocumentFormat
    let artifactHash: String
    let operation: String
    let code: String
    let status: CompatibilityExternalBlockerStatus
    let observedAt: String
    let detail: String
    let evidence: [CompatibilityEvidenceReference]
}

struct CompatibilityEvidenceSubmission: Decodable {
    let visualObservations: [CompatibilityVisualObservation]
    let clientObservations: [CompatibilityObservation]
    let externalBlockers: [CompatibilityExternalBlocker]

    static let empty = CompatibilityEvidenceSubmission(
        visualObservations: [], clientObservations: [], externalBlockers: []
    )

    private enum CodingKeys: String, CodingKey {
        case visualObservations
        case clientObservations
        case externalBlockers
    }

    init(
        visualObservations: [CompatibilityVisualObservation],
        clientObservations: [CompatibilityObservation],
        externalBlockers: [CompatibilityExternalBlocker]
    ) {
        self.visualObservations = visualObservations
        self.clientObservations = clientObservations
        self.externalBlockers = externalBlockers
    }

    init(from decoder: Decoder) throws {
        if let values = try? decoder.container(keyedBy: CodingKeys.self) {
            visualObservations = try values.decodeIfPresent(
                [CompatibilityVisualObservation].self, forKey: .visualObservations
            ) ?? []
            clientObservations = try values.decodeIfPresent(
                [CompatibilityObservation].self, forKey: .clientObservations
            ) ?? []
            externalBlockers = try values.decodeIfPresent(
                [CompatibilityExternalBlocker].self, forKey: .externalBlockers
            ) ?? []
            return
        }
        var values = try decoder.unkeyedContainer()
        var legacy: [CompatibilityObservation] = []
        while !values.isAtEnd {
            legacy.append(try values.decode(CompatibilityObservation.self))
        }
        visualObservations = []
        clientObservations = legacy
        externalBlockers = []
    }
}

struct CompatibilityReceipt: Codable {
    let corpusVersion: String
    let manifestVersion: String
    let structuralVerdict: CompatibilityVerdict
    let semanticVerdict: CompatibilityVerdict
    let visualVerdict: CompatibilityVerdict
    let clientVerdict: CompatibilityVerdict
    let overallVerdict: CompatibilityVerdict
    let requiredClientOperations: [String: [String]]
    let capabilityGaps: [String: [String]]
    let artifacts: [CompatibilityArtifact]
    let dispositions: [CompatibilityFormatDisposition]?
    let observations: [CompatibilityObservation]
    let visualObservations: [CompatibilityVisualObservation]?
    let externalBlockers: [CompatibilityExternalBlocker]?
}

struct CompatibilityCorpus: Decodable {
    let corpusVersion: String
    let manifestVersion: String
    let status: String
    let requiredFonts: [String]
    let fixtures: [CompatibilityFixture]
    let visualTolerances: CompatibilityVisualTolerances
}

struct CompatibilityVisualTolerances: Decodable {
    let pageCountDelta: Int
    let missingTextElements: Int
    let unexpectedBlankPages: Int
    let minimumTextBoundsCoverage: Double
}

struct CompatibilityFixture: Decodable {
    let id: String
    let projectPath: String
    let projectHash: String
    let capabilities: [String]
    let formats: [DocumentFormat]
}

struct FormatCapabilityResource: Decodable {
    let manifestVersion: String
    let matrix: [FormatCapabilityRow]
}

struct FormatCapabilityRow: Decodable {
    let capability: String
    let hwpx: String
    let hwp: String
    let docx: String
    let markdown: String

    func classification(for format: DocumentFormat) -> String {
        switch format {
        case .hwpx: return hwpx
        case .hwp: return hwp
        case .docx: return docx
        case .markdown: return markdown
        }
    }
}

enum CompatibilityEvidenceError: Error, LocalizedError {
    case invalidCorpus(String)
    case invalidObservation(String)

    var errorDescription: String? {
        switch self {
        case .invalidCorpus(let detail):
            return "호환성 코퍼스가 고정 계약과 일치하지 않습니다: \(detail)"
        case .invalidObservation(let detail):
            return "호환성 관찰 기록이 산출물과 일치하지 않습니다: \(detail)"
        }
    }
}
