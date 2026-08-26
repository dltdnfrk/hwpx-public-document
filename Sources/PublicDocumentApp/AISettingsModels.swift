import Foundation

enum AISettingsError: Error, LocalizedError {
    case invalidProvider
    case invalidEndpoint
    case invalidModel
    case invalidSecret
    case invalidSettings
    case notConfigured

    var errorDescription: String? {
        switch self {
        case .invalidProvider:
            "지원하지 않는 AI 제공자입니다."
        case .invalidEndpoint:
            "이 제공자에 허용되지 않는 엔드포인트입니다."
        case .invalidModel:
            "사용할 모델 이름을 입력하세요."
        case .invalidSecret:
            "제공자 자격 증명을 입력하세요."
        case .invalidSettings:
            "AI 제공자 설정 파일이 손상되었거나 지원되지 않는 버전입니다."
        case .notConfigured:
            "저장된 AI 제공자 설정이 없습니다."
        }
    }
}

struct AIProviderSetting: Codable, Equatable {
    let provider: String
    let endpointIdentity: String
    let model: String
    let keychainAccountReference: String
}

struct AISettingsFile: Codable, Equatable {
    let schemaVersion: Int
    var activeProvider: String?
    var providers: [String: AIProviderSetting]

    static let empty = AISettingsFile(schemaVersion: 1, activeProvider: nil, providers: [:])
}

struct AIProviderSettingStatus: Codable, Equatable {
    let provider: String
    let endpointIdentity: String
    let model: String
    let hasSecret: Bool
    let hostDisclosure: String
}

struct AISettingsSnapshot: Codable, Equatable {
    let activeProvider: String?
    let providers: [AIProviderSettingStatus]
    let catalog: [AIProviderPolicy]

    static let unavailable = AISettingsSnapshot(
        activeProvider: nil,
        providers: [],
        catalog: AIProviderCatalog.policies
    )
}
