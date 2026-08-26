import Foundation

extension StudioWindowController {
    func requestAIProposal(from body: [String: Any]) throws {
        let enforcement = try templateCatalogStore.enforceOfficialRules(
            in: decodeProject(from: body)
        )
        let project = enforcement.project
        guard body["consent"] as? Bool == true else { throw AIGovernanceError.consentRequired }
        let binding = try aiBinding(from: body, project: project)
        let engine = AIGovernanceEngine()
        let governed = engine.grantConsent(binding, in: project)
        try projectStore.save(governed)
        guard let setting = try? aiSettingsStore.setting(for: binding.provider) else {
            try send(enforcement: OfficialRuleEnforcement(
                project: governed,
                state: enforcement.state
            ), event: "aiProviderUnavailable")
            return
        }
        let credential = try aiSettingsStore.credential(for: setting)
        guard let payloadScope = AIPayloadScope(rawValue: binding.payloadScope) else {
            throw AIGovernanceError.consentRequired
        }
        let scopedElements = try AIGovernanceEngine.scopedElements(
            in: governed,
            scope: payloadScope,
            selectedElementIDs: body["selectedElementIDs"] as? [String] ?? []
        )
        AIProviderTransport().request(
            binding: binding,
            instruction: body["instruction"] as? String ?? "",
            elements: scopedElements,
            credential: credential
        ) { [weak self] result in
            DispatchQueue.main.async {
                guard let self else { return }
                do {
                    switch result {
                    case .success(let commands):
                        let latest = try self.projectStore.loadCanonical()
                        let proposed = try engine.propose(
                            binding: binding, commands: commands,
                            allowedTargetElementIDs: Set(scopedElements.map(\.elementID)),
                            baseRevisionID: governed.currentRevisionID, in: latest
                        ).0
                        try self.projectStore.save(proposed)
                        try self.send(enforcement: OfficialRuleEnforcement(
                            project: proposed,
                            state: enforcement.state
                        ), event: "aiProposal")
                    case .failure(let error):
                        self.send(event: "error", payload: ["message": error.localizedDescription])
                    }
                } catch {
                    self.send(event: "error", payload: ["message": error.localizedDescription])
                }
            }
        }
    }

    func configureAISettings(from body: [String: Any]) throws {
        guard let rawProvider = body["provider"] as? String,
              let provider = AIProviderKind(rawValue: rawProvider),
              let endpoint = body["endpointIdentity"] as? String,
              let model = body["model"] as? String
        else { throw AISettingsError.invalidProvider }
        _ = try aiSettingsStore.save(
            provider: provider,
            endpointIdentity: endpoint,
            model: model,
            secret: body["secret"] as? String
        )
        try send(settings: aiSettingsStore.snapshot(), event: "aiSettingsSaved")
    }

    func deleteAISettings(from body: [String: Any]) throws {
        guard let rawProvider = body["provider"] as? String,
              let provider = AIProviderKind(rawValue: rawProvider)
        else { throw AISettingsError.invalidProvider }
        try aiSettingsStore.delete(provider: provider)
        try send(settings: aiSettingsStore.snapshot(), event: "aiSettingsDeleted")
    }

    func testAISettings(from body: [String: Any]) throws {
        guard let rawProvider = body["provider"] as? String,
              let provider = AIProviderKind(rawValue: rawProvider)
        else { throw AISettingsError.invalidProvider }
        let input = try JSONSerialization.data(withJSONObject: [
            "action": "testAISettings",
            "provider": provider.rawValue,
        ])
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            guard let self else { return }
            let output = AIBridgeCLI.run(input: input, settings: self.aiSettingsStore)
            DispatchQueue.main.async {
                guard let response = try? JSONSerialization.jsonObject(with: output) as? [String: Any],
                      let events = response["events"] as? [[String: Any]]
                else {
                    self.send(event: "error", payload: ["message": AIProviderTransportError.invalidResponse.localizedDescription])
                    return
                }
                for entry in events {
                    guard let event = entry["event"] as? String,
                          let payload = entry["payload"] as? [String: Any]
                    else { continue }
                    self.send(event: event, payload: payload)
                }
            }
        }
    }

    func revokeAIConsent(from body: [String: Any]) throws {
        let enforcement = try templateCatalogStore.enforceOfficialRules(
            in: decodeProject(from: body)
        )
        var project = enforcement.project
        let binding = try aiBinding(from: body, project: project)
        let matchingGrantIDs = project.consentGrants.filter {
            !$0.revoked && $0.documentID == binding.documentID
                && $0.provider == binding.provider.rawValue
                && $0.endpointIdentity == binding.endpointIdentity
                && $0.model == binding.model
                && $0.operation == binding.operation.rawValue
                && $0.payloadScope == binding.payloadScope
        }.map(\.grantID)
        for grantID in matchingGrantIDs {
            project = AIGovernanceEngine().revokeConsent(grantID: grantID, in: project)
        }
        try projectStore.save(project)
        try send(enforcement: OfficialRuleEnforcement(
            project: project,
            state: enforcement.state
        ), event: "aiConsentRevoked")
    }

    func applyAIProposal(from body: [String: Any]) throws {
        guard let proposalID = body["proposalID"] as? String else {
            throw AIGovernanceError.proposalUnavailable
        }
        let project = try projectStore.loadCanonical()
        let commandIDs = Set(body["commandIDs"] as? [String] ?? [])
        let updated = try AIGovernanceEngine().approve(
            proposalID: proposalID, commandIDs: commandIDs, in: project
        )
        let enforcement = try templateCatalogStore.enforceOfficialRules(in: updated)
        try projectStore.save(enforcement.project)
        try send(enforcement: enforcement, event: "aiProposalApplied")
    }

    func rejectAIProposal(from body: [String: Any]) throws {
        guard let proposalID = body["proposalID"] as? String else {
            throw AIGovernanceError.proposalUnavailable
        }
        let updated = try AIGovernanceEngine().reject(
            proposalID: proposalID, in: projectStore.loadCanonical()
        )
        let enforcement = try templateCatalogStore.enforceOfficialRules(in: updated)
        try projectStore.save(enforcement.project)
        try send(enforcement: enforcement, event: "aiProposalRejected")
    }

    func undoAIRevision() throws -> DocumentProject {
        let updated = try AIGovernanceEngine().undo(in: projectStore.loadCanonical())
        try projectStore.save(updated)
        return updated
    }

    func redoAIRevision() throws -> DocumentProject {
        let updated = try AIGovernanceEngine().redo(in: projectStore.loadCanonical())
        try projectStore.save(updated)
        return updated
    }

    func aiBinding(from body: [String: Any], project: DocumentProject) throws -> AIRequestBinding {
        guard let rawProvider = body["provider"] as? String,
              let provider = AIProviderKind(rawValue: rawProvider),
              let rawOperation = body["operation"] as? String,
              let operation = AIOperation(rawValue: rawOperation),
              let payloadScope = body["payloadScope"] as? String, !payloadScope.isEmpty
        else { throw AIGovernanceError.consentRequired }
        let setting = try aiSettingsStore.setting(for: provider)
        return AIRequestBinding(
            documentID: project.documentID, provider: provider,
            endpointIdentity: setting.endpointIdentity, model: setting.model,
            operation: operation, payloadScope: payloadScope
        )
    }
}
