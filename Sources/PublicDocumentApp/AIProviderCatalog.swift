import Foundation

struct AIProviderPolicy: Codable, Equatable {
    let provider: String
    let displayName: String
    let endpointIdentity: String
    let defaultModel: String
    let endpointReadOnly: Bool
    let allowedHosts: [String]
}

enum AIProviderCatalog {
    static let policies = [
        policy(for: .openAI),
        policy(for: .anthropic),
        policy(for: .gemini),
        policy(for: .openAICompatible),
    ]

    static func policy(for provider: AIProviderKind) -> AIProviderPolicy {
        switch provider {
        case .openAI:
            AIProviderPolicy(
                provider: provider.rawValue,
                displayName: "OpenAI",
                endpointIdentity: "https://api.openai.com/v1",
                defaultModel: "gpt-5.6-terra",
                endpointReadOnly: true,
                allowedHosts: ["api.openai.com"]
            )
        case .anthropic:
            AIProviderPolicy(
                provider: provider.rawValue,
                displayName: "Anthropic",
                endpointIdentity: "https://api.anthropic.com",
                defaultModel: "claude-sonnet-5",
                endpointReadOnly: true,
                allowedHosts: ["api.anthropic.com"]
            )
        case .gemini:
            AIProviderPolicy(
                provider: provider.rawValue,
                displayName: "Gemini",
                endpointIdentity: "https://generativelanguage.googleapis.com",
                defaultModel: "gemini-2.5-flash",
                endpointReadOnly: true,
                allowedHosts: ["generativelanguage.googleapis.com"]
            )
        case .openAICompatible:
            AIProviderPolicy(
                provider: provider.rawValue,
                displayName: "OpenAI 호환 엔드포인트",
                endpointIdentity: "",
                defaultModel: "",
                endpointReadOnly: false,
                allowedHosts: []
            )
        }
    }
}
