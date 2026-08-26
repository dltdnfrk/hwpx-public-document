import Foundation

extension AIGovernanceEngine {
    func configureProvider(
        provider: AIProviderKind,
        endpointIdentity: String,
        in project: DocumentProject
    ) -> (DocumentProject, String) {
        let existing = project.providerConfigurations.first {
            $0.provider == provider.rawValue && $0.endpointIdentity == endpointIdentity
        }
        let accountReference = existing?.keychainAccountReference ?? "provider-credential-\(UUID().uuidString)"
        let retained = project.providerConfigurations.filter {
            !($0.provider == provider.rawValue && $0.endpointIdentity == endpointIdentity)
        }
        let configuration = AIProviderConfiguration(
            provider: provider.rawValue,
            endpointIdentity: endpointIdentity,
            keychainAccountReference: accountReference
        )
        return (copy(project, providerConfigurations: retained + [configuration]), accountReference)
    }

    func grantConsent(_ binding: AIRequestBinding, in project: DocumentProject) -> DocumentProject {
        let grant = AIConsentGrant(
            grantID: "consent-\(UUID().uuidString)", documentID: binding.documentID,
            provider: binding.provider.rawValue, endpointIdentity: binding.endpointIdentity,
            model: binding.model,
            operation: binding.operation.rawValue, payloadScope: binding.payloadScope, revoked: false
        )
        return copy(project, consentGrants: project.consentGrants + [grant])
    }

    func revokeConsent(grantID: String, in project: DocumentProject) -> DocumentProject {
        let grants = project.consentGrants.map { grant in
            guard grant.grantID == grantID else { return grant }
            return AIConsentGrant(
                grantID: grant.grantID, documentID: grant.documentID, provider: grant.provider,
                endpointIdentity: grant.endpointIdentity, model: grant.model, operation: grant.operation,
                payloadScope: grant.payloadScope, revoked: true
            )
        }
        return copy(project, consentGrants: grants)
    }

    func authorize(_ binding: AIRequestBinding, in project: DocumentProject) throws {
        let matched = project.consentGrants.contains { grant in
            !grant.revoked && grant.documentID == binding.documentID
                && grant.provider == binding.provider.rawValue
                && grant.endpointIdentity == binding.endpointIdentity
                && grant.model == binding.model
                && grant.operation == binding.operation.rawValue
                && grant.payloadScope == binding.payloadScope
        }
        guard matched else { throw AIGovernanceError.consentRequired }
    }

    static func scopedElements(
        in project: DocumentProject,
        scope: AIPayloadScope,
        selectedElementIDs: [String]
    ) throws -> [DocumentElement] {
        switch scope {
        case .selectedElements:
            guard !selectedElementIDs.isEmpty else { throw AIGovernanceError.consentRequired }
            let selected = Set(selectedElementIDs)
            let elements = project.elements.filter { selected.contains($0.elementID) }
            guard !elements.isEmpty else { throw AIGovernanceError.consentRequired }
            return elements
        case .evidenceAndClaims:
            return project.elements.filter { !$0.evidenceIDs.isEmpty || $0.kind == "heading" }
        case .wholeDocument:
            return project.elements
        }
    }

    func propose(
        binding: AIRequestBinding,
        commands: [AIProposalCommand],
        allowedTargetElementIDs: Set<String>,
        baseRevisionID: String? = nil,
        in project: DocumentProject
    ) throws -> (DocumentProject, [AIProposalDiff]) {
        try authorize(binding, in: project)
        let diffs = try commands.map { command -> AIProposalDiff in
            guard allowedTargetElementIDs.contains(command.targetElementID),
                  let target = project.elements.first(where: { $0.elementID == command.targetElementID }),
                  Self.valid(command, operation: binding.operation, target: target)
            else { throw AIGovernanceError.invalidProposal }
            return AIProposalDiff(
                commandID: command.commandID, targetElementID: command.targetElementID,
                before: target.text, after: command.value, targetPath: command.targetPath
            )
        }
        let proposal = AIProposalHistoryRecord(
            proposalID: "proposal-\(UUID().uuidString)", baseRevisionID: baseRevisionID ?? project.currentRevisionID,
            state: "proposed", targetElementIDs: commands.map(\.targetElementID),
            operation: binding.operation.rawValue, provider: binding.provider.rawValue,
            endpointIdentity: binding.endpointIdentity, payloadScope: binding.payloadScope,
            commands: commands, diffs: diffs
        )
        return (copy(project, aiProposalHistory: project.aiProposalHistory + [proposal]), diffs)
    }

    static func valid(_ command: AIProposalCommand, operation: AIOperation, target: DocumentElement) -> Bool {
        switch operation {
        case .missingDataMarking: return command.name == "replace-text" && command.value.contains("[확인 필요]")
        case .evidenceClaimCheck: return command.name == "evidence-check" && !target.evidenceIDs.isEmpty
        case .tableChange: return command.name == "table-cell-update" && (target.kind == "table" || target.kind == "table-cell") && parseTablePath(command.targetPath, elementID: target.elementID) != nil
        default: return command.name == "replace-text"
        }
    }

    static func parseTablePath(_ path: String?, elementID: String) -> (Int, Int)? {
        guard let path, path.hasPrefix("table:\(elementID)/") else { return nil }
        let parts = path.split(separator: "/")
        guard parts.count == 3, parts[1].hasPrefix("row:"), parts[2].hasPrefix("cell:"),
              let row = Int(parts[1].dropFirst(4)), let cell = Int(parts[2].dropFirst(5)), row >= 0, cell >= 0 else { return nil }
        return (row, cell)
    }
}
