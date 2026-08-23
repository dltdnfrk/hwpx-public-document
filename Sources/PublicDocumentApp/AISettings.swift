import Foundation

enum AISettingsError: Error, LocalizedError {
    case invalidProvider
    case invalidEndpoint
    case invalidModel
    case invalidSecret
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
        case .notConfigured:
            "저장된 AI 제공자 설정이 없습니다."
        }
    }
}

struct AIProviderDefaults {
    let endpointIdentity: String
    let model: String

    static func value(for provider: AIProviderKind) -> AIProviderDefaults {
        switch provider {
        case .openAI:
            AIProviderDefaults(endpointIdentity: "https://api.openai.com/v1", model: "gpt-5-mini")
        case .anthropic:
            AIProviderDefaults(endpointIdentity: "https://api.anthropic.com", model: "claude-sonnet-4-5")
        case .gemini:
            AIProviderDefaults(endpointIdentity: "https://generativelanguage.googleapis.com", model: "gemini-2.5-flash")
        case .openAICompatible:
            AIProviderDefaults(endpointIdentity: "", model: "")
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
}

final class AISettingsStore {
    private let root: URL
    private let credentials: AIKeychainCredentialStore
    private let fileManager: FileManager

    init(
        root: URL = AISettingsStore.defaultRoot(),
        credentials: AIKeychainCredentialStore = AIKeychainCredentialStore(),
        fileManager: FileManager = .default
    ) {
        self.root = root
        self.credentials = credentials
        self.fileManager = fileManager
    }

    static func defaultRoot() -> URL {
        if let override = ProcessInfo.processInfo.environment["PUBLIC_DOCUMENT_STUDIO_AI_SETTINGS_ROOT"] {
            return URL(fileURLWithPath: override, isDirectory: true)
        }
        return FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("PublicDocumentStudio", isDirectory: true)
    }

    func load() throws -> AISettingsFile {
        let url = root.appendingPathComponent("ai-settings.json")
        guard fileManager.fileExists(atPath: url.path) else { return .empty }
        return try JSONDecoder().decode(AISettingsFile.self, from: Data(contentsOf: url))
    }

    func setting(for provider: AIProviderKind) throws -> AIProviderSetting {
        guard let setting = try load().providers[provider.rawValue] else {
            throw AISettingsError.notConfigured
        }
        return setting
    }

    func activeSetting() throws -> AIProviderSetting {
        let settings = try load()
        guard let active = settings.activeProvider,
              let setting = settings.providers[active]
        else { throw AISettingsError.notConfigured }
        return setting
    }

    func snapshot() throws -> AISettingsSnapshot {
        let settings = try load()
        let providers = settings.providers.values.sorted { $0.provider < $1.provider }.map { setting in
            AIProviderSettingStatus(
                provider: setting.provider,
                endpointIdentity: setting.endpointIdentity,
                model: setting.model,
                hasSecret: (try? credentials.get(accountReference: setting.keychainAccountReference)) != nil,
                hostDisclosure: URL(string: setting.endpointIdentity)?.host ?? ""
            )
        }
        return AISettingsSnapshot(activeProvider: settings.activeProvider, providers: providers)
    }

    @discardableResult
    func save(
        provider: AIProviderKind,
        endpointIdentity: String,
        model: String,
        secret: String?
    ) throws -> AIProviderSetting {
        let endpoint = endpointIdentity.trimmingCharacters(in: .whitespacesAndNewlines)
            .trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        let trimmedModel = model.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let url = URL(string: endpoint),
              url.user == nil,
              url.password == nil,
              url.fragment == nil,
              AIProviderTransport.endpointIsAllowed(url, provider: provider)
        else { throw AISettingsError.invalidEndpoint }
        let allowedModelCharacters = CharacterSet.alphanumerics
            .union(CharacterSet(charactersIn: "-._:/"))
        guard !trimmedModel.isEmpty,
              trimmedModel.count <= 160,
              !trimmedModel.contains(".."),
              !trimmedModel.hasPrefix("/"),
              trimmedModel.unicodeScalars.allSatisfy({ allowedModelCharacters.contains($0) })
        else {
            throw AISettingsError.invalidModel
        }
        var settings = try load()
        let account = settings.providers[provider.rawValue]?.keychainAccountReference ?? "provider/\(provider.rawValue)"
        if let secret {
            guard !secret.isEmpty, secret.utf8.count <= 8192 else {
                throw AISettingsError.invalidSecret
            }
            try credentials.set(secret: secret, accountReference: account)
        } else if (try? credentials.get(accountReference: account)) == nil {
            throw AISettingsError.invalidSecret
        }
        let setting = AIProviderSetting(
            provider: provider.rawValue,
            endpointIdentity: endpoint,
            model: trimmedModel,
            keychainAccountReference: account
        )
        settings.providers[provider.rawValue] = setting
        settings.activeProvider = provider.rawValue
        try write(settings)
        return setting
    }

    func delete(provider: AIProviderKind) throws {
        var settings = try load()
        if let setting = settings.providers.removeValue(forKey: provider.rawValue) {
            try credentials.delete(accountReference: setting.keychainAccountReference)
        }
        if settings.activeProvider == provider.rawValue {
            settings.activeProvider = settings.providers.keys.sorted().first
        }
        try write(settings)
    }

    func credential(for setting: AIProviderSetting) throws -> String {
        try credentials.get(accountReference: setting.keychainAccountReference)
    }

    private func write(_ settings: AISettingsFile) throws {
        try fileManager.createDirectory(at: root, withIntermediateDirectories: true)
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        let url = root.appendingPathComponent("ai-settings.json")
        try encoder.encode(settings).write(to: url, options: .atomic)
        try fileManager.setAttributes([.posixPermissions: 0o600], ofItemAtPath: url.path)
    }
}

struct AIBridgeRequest: Decodable {
    let action: String
    let provider: String?
    let endpointIdentity: String?
    let model: String?
    let secret: String?
    let project: DocumentProject?
    let operation: String?
    let payloadScope: String?
    let instruction: String?
    let selectedElementIDs: [String]?
    let consent: Bool?
    let proposalID: String?
    let commandIDs: [String]?
}

enum AIBridgeCLI {
    static func run(input: Data, settings: AISettingsStore = AISettingsStore()) -> Data {
        do {
            let request = try JSONDecoder().decode(AIBridgeRequest.self, from: input)
            let events = try handle(request, settings: settings)
            return try JSONSerialization.data(withJSONObject: ["events": events])
        } catch {
            let message = (error as? LocalizedError)?.errorDescription ?? "AI 제공자 작업을 완료하지 못했습니다."
            return (try? JSONSerialization.data(withJSONObject: [
                "events": [["event": "error", "payload": ["message": message]]],
            ])) ?? Data("{\"events\":[]}".utf8)
        }
    }

    private static func handle(
        _ request: AIBridgeRequest,
        settings: AISettingsStore
    ) throws -> [[String: Any]] {
        switch request.action {
        case "loadAISettings":
            return [try event("aiSettingsLoaded", project: try settings.snapshot())]
        case "configureAISettings":
            let provider = try provider(from: request)
            guard let endpoint = request.endpointIdentity,
                  let model = request.model
            else { throw AISettingsError.invalidEndpoint }
            _ = try settings.save(
                provider: provider,
                endpointIdentity: endpoint,
                model: model,
                secret: request.secret
            )
            return [try event("aiSettingsSaved", project: try settings.snapshot())]
        case "deleteAISettings":
            let provider = try provider(from: request)
            try settings.delete(provider: provider)
            return [try event("aiSettingsDeleted", project: try settings.snapshot())]
        case "testAISettings":
            let provider = try provider(from: request)
            let setting = try settings.setting(for: provider)
            let commands = try requestCommands(
                setting: setting,
                credential: try settings.credential(for: setting),
                operation: .summarize,
                scope: "selected-elements",
                instruction: "연결 확인용 JSON 명령 하나를 반환하세요.",
                elements: [DocumentElement(
                    elementID: "connection-test",
                    kind: "paragraph",
                    order: 0,
                    text: "connection test",
                    styleID: "style-body",
                    evidenceIDs: []
                )]
            )
            guard !commands.isEmpty else { throw AIProviderTransportError.invalidResponse }
            return [try event("aiSettingsTested", project: try settings.snapshot())]
        case "requestAIProposal":
            return try requestProposal(request, settings: settings)
        case "applyAIProposal":
            guard let project = request.project,
                  let proposalID = request.proposalID
            else { throw AIGovernanceError.invalidProposal }
            let updated = try AIGovernanceEngine().approve(
                proposalID: proposalID,
                commandIDs: Set(request.commandIDs ?? []),
                in: project
            )
            return [try event("aiProposalApplied", project: updated)]
        case "rejectAIProposal":
            guard let project = request.project,
                  let proposalID = request.proposalID
            else { throw AIGovernanceError.invalidProposal }
            let updated = try AIGovernanceEngine().reject(proposalID: proposalID, in: project)
            return [try event("aiProposalRejected", project: updated)]
        case "revokeAIConsent":
            guard let project = request.project else { throw AIGovernanceError.invalidProposal }
            let provider = try provider(from: request)
            let setting = try settings.setting(for: provider)
            let binding = try binding(request, project: project, setting: setting)
            let grant = project.consentGrants.last {
                !$0.revoked
                    && $0.documentID == binding.documentID
                    && $0.provider == binding.provider.rawValue
                    && $0.endpointIdentity == binding.endpointIdentity
                    && $0.operation == binding.operation.rawValue
                    && $0.payloadScope == binding.payloadScope
            }
            let updated = grant.map {
                AIGovernanceEngine().revokeConsent(grantID: $0.grantID, in: project)
            } ?? project
            return [try event("aiConsentRevoked", project: updated)]
        default:
            throw AISettingsError.invalidProvider
        }
    }

    private static func requestProposal(
        _ request: AIBridgeRequest,
        settings: AISettingsStore
    ) throws -> [[String: Any]] {
        guard request.consent == true, let project = request.project else {
            throw AIGovernanceError.consentRequired
        }
        let provider = try provider(from: request)
        let setting = try settings.setting(for: provider)
        let binding = try binding(request, project: project, setting: setting)
        let elements = try scopedElements(
            project: project,
            scope: binding.payloadScope,
            selectedElementIDs: request.selectedElementIDs ?? []
        )
        let governed = AIGovernanceEngine().grantConsent(binding, in: project)
        let commands = try requestCommands(
            setting: setting,
            credential: try settings.credential(for: setting),
            operation: binding.operation,
            scope: binding.payloadScope,
            instruction: request.instruction ?? "",
            elements: elements
        )
        let proposal = try AIGovernanceEngine().propose(
            binding: binding,
            commands: commands,
            allowedTargetElementIDs: Set(elements.map(\.elementID)),
            baseRevisionID: governed.currentRevisionID,
            in: governed
        ).0
        return [try event("aiProposal", project: proposal)]
    }

    private static func provider(from request: AIBridgeRequest) throws -> AIProviderKind {
        guard let raw = request.provider,
              let provider = AIProviderKind(rawValue: raw)
        else { throw AISettingsError.invalidProvider }
        return provider
    }

    private static func binding(
        _ request: AIBridgeRequest,
        project: DocumentProject,
        setting: AIProviderSetting
    ) throws -> AIRequestBinding {
        guard let provider = AIProviderKind(rawValue: setting.provider),
              let operationRaw = request.operation,
              let operation = AIOperation(rawValue: operationRaw),
              let scope = request.payloadScope,
              !scope.isEmpty
        else { throw AIGovernanceError.consentRequired }
        return AIRequestBinding(
            documentID: project.documentID,
            provider: provider,
            endpointIdentity: setting.endpointIdentity,
            model: setting.model,
            operation: operation,
            payloadScope: scope
        )
    }

    private static func scopedElements(
        project: DocumentProject,
        scope: String,
        selectedElementIDs: [String]
    ) throws -> [DocumentElement] {
        switch scope {
        case "selected-elements":
            guard !selectedElementIDs.isEmpty else { throw AIGovernanceError.consentRequired }
            let selected = Set(selectedElementIDs)
            return project.elements.filter { selected.contains($0.elementID) }
        case "evidence-and-claims":
            return project.elements.filter { !$0.evidenceIDs.isEmpty || $0.kind == "heading" }
        case "whole-document":
            return project.elements
        default:
            throw AIGovernanceError.consentRequired
        }
    }

    private static func requestCommands(
        setting: AIProviderSetting,
        credential: String,
        operation: AIOperation,
        scope: String,
        instruction: String,
        elements: [DocumentElement]
    ) throws -> [AIProposalCommand] {
        guard let provider = AIProviderKind(rawValue: setting.provider) else {
            throw AISettingsError.invalidProvider
        }
        let semaphore = DispatchSemaphore(value: 0)
        var result: Result<[AIProposalCommand], Error> = .failure(AIProviderTransportError.invalidResponse)
        AIProviderTransport().request(
            binding: AIRequestBinding(
                documentID: "settings-request",
                provider: provider,
                endpointIdentity: setting.endpointIdentity,
                model: setting.model,
                operation: operation,
                payloadScope: scope
            ),
            instruction: instruction,
            elements: elements,
            credential: credential
        ) {
            result = $0
            semaphore.signal()
        }
        guard semaphore.wait(timeout: .now() + 90) == .success else {
            throw AIProviderTransportError.invalidResponse
        }
        return try result.get()
    }

    private static func event<T: Encodable>(_ name: String, project: T) throws -> [String: Any] {
        let data = try JSONEncoder().encode(project)
        let object = try JSONSerialization.jsonObject(with: data)
        return ["event": name, "payload": ["project": object]]
    }

    private static func event(_ name: String, project: [String: Any]) -> [String: Any] {
        ["event": name, "payload": ["project": project]]
    }
}
