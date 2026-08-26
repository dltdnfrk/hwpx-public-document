import Foundation

struct LegacyDocumentProject: Codable {
    let schemaVersion: Int
    let documentID: String
    let locale: String
    let title: String
    let currentRevisionID: String
    let elements: [DocumentElement]
    let assets: [DocumentAsset]
    let styles: [DocumentStyle]
    let templateBinding: ProjectTemplateBinding
    let evidenceLinks: [SourceEvidenceLink]
    let revisions: [DocumentRevision]
    let history: [ProjectHistoryEvent]
}

enum ProjectStoreError: Error, LocalizedError {
    case unsupportedSchema(Int)
    case invalidProject

    var errorDescription: String? {
        switch self {
        case .unsupportedSchema(let version):
            return "지원하지 않는 프로젝트 스키마 버전입니다: \(version)"
        case .invalidProject:
            return "프로젝트 파일을 읽을 수 없습니다."
        }
    }
}

struct ProjectInspection: Codable {
    let schemaVersion: Int
    let documentID: String
    let currentRevisionID: String
    let elementCount: Int
    let assetCount: Int
    let styleCount: Int
    let evidenceLinkCount: Int
    let revisionCount: Int
    let historyEventCount: Int
    let templateID: String
    let templateVersion: String
}
