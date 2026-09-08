import Foundation

extension AIGovernanceEngine {
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
        var replacements: [String: DocumentElement] = [:]
        for command in selected {
            guard let target = replacements[command.targetElementID]
                    ?? project.elements.first(where: { $0.elementID == command.targetElementID }),
                  Self.valid(command, operation: AIOperation(rawValue: proposal.operation) ?? .freeForm, target: target)
            else { throw AIGovernanceError.invalidProposal }
            let text: String
            let html: String
            if command.name == "table-cell-update" {
                guard let path = Self.parseTablePath(command.targetPath, elementID: target.elementID),
                      let updated = Self.replaceTableCell(in: target.contentHTML, row: path.0, cell: path.1, value: command.value)
                else { throw AIGovernanceError.invalidProposal }
                html = updated
                text = Self.plainText(updated)
            } else {
                text = command.value
                html = command.value
            }
            replacements[target.elementID] = DocumentElement(
                elementID: target.elementID, kind: target.kind, order: target.order,
                text: text, contentHTML: html, inlineIDs: target.inlineIDs,
                styleID: target.styleID, evidenceIDs: target.evidenceIDs
            )
        }
        let elements = project.elements.map { replacements[$0.elementID] ?? $0 }
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
}
