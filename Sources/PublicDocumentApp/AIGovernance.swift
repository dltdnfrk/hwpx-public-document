import Foundation

enum AIProviderKind: String, CaseIterable, Codable {
    case anthropic
    case gemini
    case openAI = "openai"
    case openAICompatible = "openai-compatible"
}

enum AIOperation: String, Codable {
    case sourceGroundedDraft = "source-grounded-draft"
    case templateCompletion = "template-completion"
    case missingDataMarking = "missing-data-marking"
    case summarize
    case rewrite
    case translate
    case publicLanguageCorrection = "public-language-correction"
    case styleCorrection = "style-correction"
    case tableChange = "table-change"
    case evidenceClaimCheck = "evidence-claim-check"
    case freeForm = "free-form"
}

struct AIRequestBinding: Equatable {
    let documentID: String
    let provider: AIProviderKind
    let endpointIdentity: String
    let operation: AIOperation
    let payloadScope: String
}

enum AIGovernanceError: Error, LocalizedError {
    case consentRequired
    case staleProposal
    case invalidProposal
    case proposalUnavailable
    case undoUnavailable
    case redoUnavailable

    var errorDescription: String? {
        switch self {
        case .consentRequired: return "문서, 제공자, 엔드포인트, 작업 및 전송 범위에 맞는 동의가 필요합니다."
        case .staleProposal: return "제안 기준 리비전이 현재 문서와 달라 적용할 수 없습니다."
        case .invalidProposal: return "스키마 또는 대상 요소가 유효하지 않아 제안을 적용할 수 없습니다."
        case .proposalUnavailable: return "검토할 AI 제안을 찾을 수 없습니다."
        case .undoUnavailable: return "실행 취소할 AI 리비전이 없습니다."
        case .redoUnavailable: return "다시 실행할 AI 리비전이 없습니다."
        }
    }
}

struct AIProposalDiff: Codable, Equatable {
    let commandID: String
    let targetElementID: String
    let before: String
    let after: String
    let targetPath: String?
}

struct AIGovernanceEngine {
    static let approvedProviderKinds = AIProviderKind.allCases

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
            operation: binding.operation.rawValue, payloadScope: binding.payloadScope, revoked: false
        )
        return copy(project, consentGrants: project.consentGrants + [grant])
    }

    func revokeConsent(grantID: String, in project: DocumentProject) -> DocumentProject {
        let grants = project.consentGrants.map { grant in
            guard grant.grantID == grantID else { return grant }
            return AIConsentGrant(
                grantID: grant.grantID, documentID: grant.documentID, provider: grant.provider,
                endpointIdentity: grant.endpointIdentity, operation: grant.operation,
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
                && grant.operation == binding.operation.rawValue
                && grant.payloadScope == binding.payloadScope
        }
        guard matched else { throw AIGovernanceError.consentRequired }
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

    private static func valid(_ command: AIProposalCommand, operation: AIOperation, target: DocumentElement) -> Bool {
        switch operation {
        case .missingDataMarking: return command.name == "replace-text" && command.value.contains("[확인 필요]")
        case .evidenceClaimCheck: return command.name == "evidence-check" && !target.evidenceIDs.isEmpty
        case .tableChange: return command.name == "table-cell-update" && (target.kind == "table" || target.kind == "table-cell") && parseTablePath(command.targetPath, elementID: target.elementID) != nil
        default: return command.name == "replace-text"
        }
    }

    private static func parseTablePath(_ path: String?, elementID: String) -> (Int, Int)? {
        guard let path, path.hasPrefix("table:\(elementID)/") else { return nil }
        let parts = path.split(separator: "/")
        guard parts.count == 3, parts[1].hasPrefix("row:"), parts[2].hasPrefix("cell:"),
              let row = Int(parts[1].dropFirst(4)), let cell = Int(parts[2].dropFirst(5)), row >= 0, cell >= 0 else { return nil }
        return (row, cell)
    }

    func reject(proposalID: String, in project: DocumentProject) throws -> DocumentProject {
        try updateProposal(proposalID: proposalID, state: "rejected", approved: [], revisionID: nil, in: project)
    }

    func approve(
        proposalID: String,
        commandIDs: Set<String>?,
        in project: DocumentProject
    ) throws -> DocumentProject {
        guard let proposal = project.aiProposalHistory.first(where: { $0.proposalID == proposalID && $0.state == "proposed" })
        else { throw AIGovernanceError.proposalUnavailable }
        guard proposal.baseRevisionID == project.currentRevisionID else { throw AIGovernanceError.staleProposal }
        let selected = commandIDs.map { ids in proposal.commands.filter { ids.contains($0.commandID) } } ?? proposal.commands
        guard !selected.isEmpty, Set(selected.map(\.commandID)).count == (commandIDs?.count ?? selected.count)
        else { throw AIGovernanceError.invalidProposal }
        var replacements: [String: String] = [:]
        for command in selected {
            guard let target = project.elements.first(where: { $0.elementID == command.targetElementID }),
                  Self.valid(command, operation: AIOperation(rawValue: proposal.operation) ?? .freeForm, target: target)
            else { throw AIGovernanceError.invalidProposal }
            replacements[command.targetElementID] = command.value
        }
        let elements = project.elements.map { element in
            guard let value = replacements[element.elementID] else { return element }
            if let command = selected.first(where: { $0.targetElementID == element.elementID }), command.name == "table-cell-update",
               let path = Self.parseTablePath(command.targetPath, elementID: element.elementID),
               let html = Self.replaceTableCell(in: element.contentHTML, row: path.0, cell: path.1, value: value) {
                return DocumentElement(elementID: element.elementID, kind: element.kind, order: element.order, text: Self.plainText(html), contentHTML: html, inlineIDs: element.inlineIDs, styleID: element.styleID, evidenceIDs: element.evidenceIDs)
            }
            return DocumentElement(
                elementID: element.elementID, kind: element.kind, order: element.order,
                text: value, contentHTML: value, inlineIDs: element.inlineIDs,
                styleID: element.styleID, evidenceIDs: element.evidenceIDs
            )
        }
        let revisionID = "revision-\(UUID().uuidString)"
        let revision = DocumentRevision(
            revisionID: revisionID, parentRevisionID: project.currentRevisionID,
            createdAt: ISO8601DateFormatter().string(from: Date()), summary: "ai-proposal-approved",
            elementIDs: elements.map(\.elementID), snapshotElements: elements
        )
        let withRevision = copy(
            project, currentRevisionID: revisionID, elements: elements,
            revisions: project.revisions + [revision], redoRevisionIDs: []
        )
        return try updateProposal(
            proposalID: proposalID,
            state: selected.count == proposal.commands.count ? "approved" : "partially-approved",
            approved: selected.map(\.commandID), revisionID: revisionID, in: withRevision
        )
    }

    private static func replaceTableCell(in html: String, row: Int, cell: Int, value: String) -> String? {
        let rows = try? NSRegularExpression(pattern: "(?is)<tr\\b[^>]*>.*?</tr>")
        guard let rows else { return nil }
        let matches = rows.matches(in: html, range: NSRange(html.startIndex..., in: html))
        guard row < matches.count, let rr = Range(matches[row].range, in: html) else { return nil }
        let rowHTML = String(html[rr]); let cells = try? NSRegularExpression(pattern: "(?is)<(td|th)\\b[^>]*>.*?</\\1>")
        guard let cells else { return nil }; let cm = cells.matches(in: rowHTML, range: NSRange(rowHTML.startIndex..., in: rowHTML))
        guard cell < cm.count, let cr = Range(cm[cell].range, in: rowHTML) else { return nil }
        let old = String(rowHTML[cr]); guard let openEnd = old.firstIndex(of: ">"), let close = old.range(of: "</", options: .backwards) else { return nil }
        let updated = old[..<old.index(after: openEnd)] + value + old[close.lowerBound...]
        let newRow = rowHTML[..<cr.lowerBound] + updated + rowHTML[cr.upperBound...]
        return String(html[..<rr.lowerBound]) + newRow + String(html[rr.upperBound...])
    }

    private static func plainText(_ html: String) -> String {
        html.replacingOccurrences(of: "<[^>]+>", with: " ", options: .regularExpression).replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression).trimmingCharacters(in: .whitespacesAndNewlines)
    }

    func undo(in project: DocumentProject) throws -> DocumentProject {
        guard let current = project.revisions.first(where: { $0.revisionID == project.currentRevisionID }),
              let parentID = current.parentRevisionID,
              let parent = project.revisions.first(where: { $0.revisionID == parentID }),
              !parent.snapshotElements.isEmpty
        else { throw AIGovernanceError.undoUnavailable }
        return copy(
            project, currentRevisionID: parentID, elements: parent.snapshotElements,
            redoRevisionIDs: project.redoRevisionIDs + [current.revisionID]
        )
    }

    func redo(in project: DocumentProject) throws -> DocumentProject {
        guard let revisionID = project.redoRevisionIDs.last,
              let revision = project.revisions.first(where: { $0.revisionID == revisionID }),
              revision.parentRevisionID == project.currentRevisionID, !revision.snapshotElements.isEmpty
        else { throw AIGovernanceError.redoUnavailable }
        return copy(
            project, currentRevisionID: revisionID, elements: revision.snapshotElements,
            redoRevisionIDs: Array(project.redoRevisionIDs.dropLast())
        )
    }

    private func updateProposal(
        proposalID: String, state: String, approved: [String], revisionID: String?,
        in project: DocumentProject
    ) throws -> DocumentProject {
        guard project.aiProposalHistory.contains(where: { $0.proposalID == proposalID })
        else { throw AIGovernanceError.proposalUnavailable }
        let proposals = project.aiProposalHistory.map { proposal in
            guard proposal.proposalID == proposalID else { return proposal }
            return AIProposalHistoryRecord(
                proposalID: proposal.proposalID, baseRevisionID: proposal.baseRevisionID, state: state,
                targetElementIDs: proposal.targetElementIDs, operation: proposal.operation,
                provider: proposal.provider, endpointIdentity: proposal.endpointIdentity,
                payloadScope: proposal.payloadScope, commands: proposal.commands, diffs: proposal.diffs,
                approvedCommandIDs: approved, createdRevisionID: revisionID
            )
        }
        return copy(project, aiProposalHistory: proposals)
    }

    private func copy(
        _ project: DocumentProject,
        currentRevisionID: String? = nil,
        elements: [DocumentElement]? = nil,
        revisions: [DocumentRevision]? = nil,
        aiProposalHistory: [AIProposalHistoryRecord]? = nil,
        providerConfigurations: [AIProviderConfiguration]? = nil,
        consentGrants: [AIConsentGrant]? = nil,
        redoRevisionIDs: [String]? = nil
    ) -> DocumentProject {
        DocumentProject(
            schemaVersion: project.schemaVersion, documentID: project.documentID, locale: project.locale,
            title: project.title, currentRevisionID: currentRevisionID ?? project.currentRevisionID,
            elements: elements ?? project.elements, assets: project.assets, styles: project.styles,
            templateBinding: project.templateBinding, evidenceLinks: project.evidenceLinks,
            revisions: revisions ?? project.revisions, history: project.history,
            aiProposalHistory: aiProposalHistory ?? project.aiProposalHistory,
            providerConfigurations: providerConfigurations ?? project.providerConfigurations,
            consentGrants: consentGrants ?? project.consentGrants,
            redoRevisionIDs: redoRevisionIDs ?? project.redoRevisionIDs
        )
    }
}
