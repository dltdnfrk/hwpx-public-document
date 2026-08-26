import Foundation

struct CatalogOfficialRule: Codable, Equatable {
    let field: CatalogOfficialField
    let precedence: Int
    let requiredValue: String
    let source: String
}

struct OfficialRuleConflict: Codable, Equatable {
    let field: CatalogOfficialField
    let submittedValue: String
    let requiredValue: String
    let precedence: Int
    let source: String
    let warning: String
}

struct OfficialRuleEnforcementState: Codable, Equatable {
    let appliedRules: [CatalogOfficialRule]
    let conflicts: [OfficialRuleConflict]
    let contentChanged: Bool
}

struct OfficialRuleEnforcement {
    let project: DocumentProject
    let state: OfficialRuleEnforcementState
}

struct TemplateCatalogEntry: Codable, Equatable {
    let templateID: String
    let version: String
    let effectiveDate: String
    let publishingAuthority: String
    let source: String
    let contentHash: String
    let documentType: String
    let requiredSections: [String]
    let checklist: [String]
    let officialRules: [CatalogOfficialRule]
}

struct TemplateCatalogPayload: Codable, Equatable {
    let catalogID: String
    let version: String
    let publishedAt: String
    let entries: [TemplateCatalogEntry]
}

struct TemplateCatalogEnvelope: Codable {
    let keyID: String
    let payload: String
    let signature: String
}

struct TemplateCatalogStatus: Codable {
    let catalogVersion: String
    let publishedAt: String
    let entries: [TemplateCatalogEntry]
    let rollbackAvailable: Bool
}

struct TemplateCatalogHistoryEvent: Codable {
    let catalogVersion: String
    let kind: String
    let recordedAt: String
}

enum TemplateCatalogError: Error, LocalizedError {
    case invalidEnvelope
    case invalidSignature
    case noTrustedCatalog
    case noRollbackCatalog

    var errorDescription: String? {
        switch self {
        case .invalidEnvelope:
            return "템플릿 카탈로그 형식이 올바르지 않습니다."
        case .invalidSignature:
            return "템플릿 카탈로그 서명을 확인할 수 없습니다. 마지막 신뢰 카탈로그를 유지합니다."
        case .noTrustedCatalog:
            return "오프라인에서 사용할 신뢰 템플릿 카탈로그가 없습니다."
        case .noRollbackCatalog:
            return "되돌릴 이전 템플릿 카탈로그가 없습니다."
        }
    }
}
