import Foundation

extension TemplateCatalogStore {
    private func replacingOfficialTitle(in element: DocumentElement, with title: String) -> DocumentElement {
        // Rich source is preferred by the editor; changing only .text leaves a stale title.
        let document = try? XMLDocument(
            xmlString: "<title-root>\(element.contentHTML)</title-root>",
            options: [.nodePreserveAll, .nodeLoadExternalEntitiesNever]
        )
        let root = document?.rootElement()
        if element.text == title && (element.contentHTML.isEmpty || root?.stringValue == title) {
            return element
        }
        var html = title.replacingOccurrences(of: "&", with: "&amp;")
            .replacingOccurrences(of: "<", with: "&lt;")
            .replacingOccurrences(of: ">", with: "&gt;")
        var inlineIDs: [String] = []
        if let root, let run = singleOfficialTitleRun(root) {
            run.text.stringValue = title
            html = root.children!.map(\.xmlString).joined()
            inlineIDs = run.inlineIDs
        }
        // A single safe formatting chain still identifies this title. Malformed,
        // unsafe, or multi-run source becomes literal title text under the rule;
        // obsolete inline identities remain only in the original revision snapshot.
        return DocumentElement(
            elementID: element.elementID, kind: element.kind, order: element.order,
            text: title, contentHTML: html, inlineIDs: inlineIDs,
            styleID: element.styleID, evidenceIDs: element.evidenceIDs
        )
    }

    private func singleOfficialTitleRun(_ root: XMLElement) -> (text: XMLNode, inlineIDs: [String])? {
        let formattingTags: Set<String> = ["span", "strong", "b", "em", "i", "u"]
        var current: XMLNode = root
        var inlineIDs: [String] = []
        while let container = current as? XMLElement {
            guard let children = container.children, children.count == 1 else { return nil }
            current = children[0]
            if let inline = current as? XMLElement {
                guard formattingTags.contains(inline.name ?? ""),
                      (inline.attributes ?? []).allSatisfy({ $0.name == "data-inline-id" })
                else { return nil }
                if let id = inline.attribute(forName: "data-inline-id")?.stringValue {
                    inlineIDs.append(id)
                }
            }
        }
        guard current.kind == .text else { return nil }
        return (current, inlineIDs)
    }

    func officialRuleEnforcement(in project: DocumentProject) throws -> OfficialRuleEnforcement {
        let status = try currentStatus()
        let rules = highestPrecedenceRules(
            in: status.entries,
            templateID: project.templateBinding.templateID
        )
        let catalog = TemplateCatalogPayload(
            catalogID: "public-document-templates",
            version: status.catalogVersion,
            publishedAt: status.publishedAt,
            entries: status.entries
        )
        var authoritativeTitle = project.title
        var authoritativeElements = project.elements
        var conflicts: [OfficialRuleConflict] = []
        var changedFields: [CatalogOfficialField] = []

        for rule in rules {
            switch rule.field {
            case .title:
                let corrected = authoritativeElements.map { element in
                    isTitleElement(element)
                        ? replacingOfficialTitle(in: element, with: rule.requiredValue)
                        : element
                }
                guard authoritativeTitle != rule.requiredValue || corrected != authoritativeElements else { continue }
                let changedTitle = zip(authoritativeElements, corrected).first { $0 != $1 }?.0
                let submittedValue = authoritativeTitle != rule.requiredValue
                    ? authoritativeTitle
                    : changedTitle.map { $0.text == rule.requiredValue ? $0.contentHTML : $0.text } ?? authoritativeTitle
                authoritativeTitle = rule.requiredValue
                authoritativeElements = corrected
                conflicts.append(OfficialRuleConflict(
                    field: rule.field,
                    submittedValue: submittedValue,
                    requiredValue: rule.requiredValue,
                    precedence: rule.precedence,
                    source: rule.source,
                    warning: "공식 규칙 충돌: 제출 제목 '\(submittedValue)' 대신 공식 규칙(우선순위 \(rule.precedence))의 필수 제목을 적용했습니다: '\(rule.requiredValue)'."
                ))
                changedFields.append(.title)
            case .endMark, .attachment, .senderName:
                let working = DocumentProject(
                    schemaVersion: project.schemaVersion,
                    documentID: project.documentID,
                    locale: project.locale,
                    title: authoritativeTitle,
                    currentRevisionID: project.currentRevisionID,
                    elements: authoritativeElements,
                    assets: project.assets,
                    styles: project.styles,
                    templateBinding: project.templateBinding,
                    evidenceLinks: project.evidenceLinks,
                    revisions: project.revisions,
                    history: project.history,
                    aiProposalHistory: project.aiProposalHistory,
                    providerConfigurations: project.providerConfigurations,
                    consentGrants: project.consentGrants,
                    redoRevisionIDs: project.redoRevisionIDs
                )
                guard let applied = OfficialRuleSkeleton.apply(rule: rule, to: working) else { continue }
                authoritativeElements = applied.elements
                conflicts.append(applied.conflict)
                changedFields.append(rule.field)
            }
        }

        let draft = DocumentProject(
            schemaVersion: project.schemaVersion,
            documentID: project.documentID,
            locale: project.locale,
            title: authoritativeTitle,
            currentRevisionID: project.currentRevisionID,
            elements: authoritativeElements,
            assets: project.assets,
            styles: project.styles,
            templateBinding: project.templateBinding,
            evidenceLinks: project.evidenceLinks,
            revisions: project.revisions,
            history: project.history,
            aiProposalHistory: project.aiProposalHistory,
            providerConfigurations: project.providerConfigurations,
            consentGrants: project.consentGrants,
            redoRevisionIDs: project.redoRevisionIDs
        )
        let styleLint = OfficialStyleLint.dryRun(project: draft, catalog: catalog)
        guard authoritativeTitle != project.title || authoritativeElements != project.elements else {
            return OfficialRuleEnforcement(
                project: project,
                state: OfficialRuleEnforcementState(
                    appliedRules: rules,
                    conflicts: conflicts,
                    contentChanged: false,
                    styleLint: styleLint
                )
            )
        }

        let createdAt = ISO8601DateFormatter().string(from: Date())
        let revisionID = "revision-official-rule-\(UUID().uuidString.lowercased())"
        let kind = "official-rule-enforced:" + changedFields.map(\.rawValue).joined(separator: ",")
        let revision = DocumentRevision(
            revisionID: revisionID,
            parentRevisionID: project.currentRevisionID,
            createdAt: createdAt,
            summary: kind,
            elementIDs: authoritativeElements.map(\.elementID),
            snapshotElements: authoritativeElements
        )
        let historyEvent = ProjectHistoryEvent(
            eventID: "history-official-rule-\(UUID().uuidString.lowercased())",
            kind: kind,
            revisionID: revisionID,
            createdAt: createdAt
        )
        let governed = DocumentProject(
            schemaVersion: project.schemaVersion,
            documentID: project.documentID,
            locale: project.locale,
            title: authoritativeTitle,
            currentRevisionID: revisionID,
            elements: authoritativeElements,
            assets: project.assets,
            styles: project.styles,
            templateBinding: project.templateBinding,
            evidenceLinks: project.evidenceLinks,
            revisions: project.revisions + [revision],
            history: project.history + [historyEvent],
            aiProposalHistory: project.aiProposalHistory,
            providerConfigurations: project.providerConfigurations,
            consentGrants: project.consentGrants,
            redoRevisionIDs: project.redoRevisionIDs
        )
        return OfficialRuleEnforcement(
            project: governed,
            state: OfficialRuleEnforcementState(
                appliedRules: rules,
                conflicts: conflicts,
                contentChanged: true,
                styleLint: OfficialStyleLint.dryRun(project: governed, catalog: catalog)
            )
        )
    }
}
