import Foundation

private enum AIBridgeAction: String, Decodable {
    case loadAISettings
    case configureAISettings
    case deleteAISettings
    case testAISettings
    case requestAIProposal
    case applyAIProposal
    case rejectAIProposal
    case revokeAIConsent
}

private struct AIBridgeRequest: Decodable {
    let action: AIBridgeAction
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
            let message = (error as? LocalizedError)?.errorDescription
                ?? "AI 제공자 작업을 완료하지 못했습니다."
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
        case .loadAISettings:
            if let project = request.project {
                _ = try settings.migrateLegacyConfigurations(project.providerConfigurations)
            }
            return [try settingsEvent("aiSettingsLoaded", snapshot: try settings.snapshot())]
        case .configureAISettings:
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
            return [try settingsEvent("aiSettingsSaved", snapshot: try settings.snapshot())]
        case .deleteAISettings:
            let provider = try provider(from: request)
            try settings.delete(provider: provider)
            return [try settingsEvent("aiSettingsDeleted", snapshot: try settings.snapshot())]
        case .testAISettings:
            let provider = try provider(from: request)
            let setting = try settings.setting(for: provider)
            let commands = try requestCommands(
                setting: setting,
                credential: try settings.credential(for: setting),
                documentID: "connection-test",
                operation: .summarize,
                scope: AIPayloadScope.selectedElements.rawValue,
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
            return [try settingsEvent("aiSettingsTested", snapshot: try settings.snapshot())]
        case .requestAIProposal:
            return try requestProposal(request, settings: settings)
        case .applyAIProposal:
            guard let project = request.project,
                  let proposalID = request.proposalID
            else { throw AIGovernanceError.invalidProposal }
            let updated = try AIGovernanceEngine().approve(
                proposalID: proposalID,
                commandIDs: Set(request.commandIDs ?? []),
                in: project
            )
            return [try projectEvent("aiProposalApplied", project: updated)]
        case .rejectAIProposal:
            guard let project = request.project,
                  let proposalID = request.proposalID
            else { throw AIGovernanceError.invalidProposal }
            let updated = try AIGovernanceEngine().reject(proposalID: proposalID, in: project)
            return [try projectEvent("aiProposalRejected", project: updated)]
        case .revokeAIConsent:
            guard let project = request.project else { throw AIGovernanceError.invalidProposal }
            let provider = try provider(from: request)
            let setting = try settings.setting(for: provider)
            let binding = try binding(request, project: project, setting: setting)
            let grant = project.consentGrants.last {
                !$0.revoked
                    && $0.documentID == binding.documentID
                    && $0.provider == binding.provider.rawValue
                    && $0.endpointIdentity == binding.endpointIdentity
                    && $0.model == binding.model
                    && $0.operation == binding.operation.rawValue
                    && $0.payloadScope == binding.payloadScope
            }
            let updated = grant.map {
                AIGovernanceEngine().revokeConsent(grantID: $0.grantID, in: project)
            } ?? project
            return [try projectEvent("aiConsentRevoked", project: updated)]
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
        guard let payloadScope = AIPayloadScope(rawValue: binding.payloadScope) else {
            throw AIGovernanceError.consentRequired
        }
        let elements = try AIGovernanceEngine.scopedElements(
            in: project,
            scope: payloadScope,
            selectedElementIDs: request.selectedElementIDs ?? []
        )
        let governed = AIGovernanceEngine().grantConsent(binding, in: project)
        let commands = try requestCommands(
            setting: setting,
            credential: try settings.credential(for: setting),
            documentID: project.documentID,
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
        return [try projectEvent("aiProposal", project: proposal)]
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
              AIPayloadScope(rawValue: scope) != nil
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

    private static func requestCommands(
        setting: AIProviderSetting,
        credential: String,
        documentID: String,
        operation: AIOperation,
        scope: String,
        instruction: String,
        elements: [DocumentElement]
    ) throws -> [AIProposalCommand] {
        guard let provider = AIProviderKind(rawValue: setting.provider) else {
            throw AISettingsError.invalidProvider
        }
        let semaphore = DispatchSemaphore(value: 0)
        var result: Result<[AIProposalCommand], Error> = .failure(
            AIProviderTransportError.invalidResponse
        )
        AIProviderTransport().request(
            binding: AIRequestBinding(
                documentID: documentID,
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

    private static func settingsEvent(
        _ name: String,
        snapshot: AISettingsSnapshot
    ) throws -> [String: Any] {
        let data = try JSONEncoder().encode(snapshot)
        let object = try JSONSerialization.jsonObject(with: data)
        return ["event": name, "payload": ["settings": object]]
    }

    private static func projectEvent(
        _ name: String,
        project: DocumentProject
    ) throws -> [String: Any] {
        let data = try JSONEncoder().encode(project)
        let object = try JSONSerialization.jsonObject(with: data)
        return ["event": name, "payload": ["project": object]]
    }
}
