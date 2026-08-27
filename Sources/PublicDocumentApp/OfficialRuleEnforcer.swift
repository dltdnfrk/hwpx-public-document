import Foundation

extension TemplateCatalogStore {
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
                let titleElements = authoritativeElements.filter(isTitleElement)
                let submittedValue = authoritativeTitle != rule.requiredValue
                    ? authoritativeTitle
                    : titleElements.first(where: { $0.text != rule.requiredValue })?.text
                guard let submittedValue else { continue }
                authoritativeTitle = rule.requiredValue
                authoritativeElements = authoritativeElements.map { element in
                    guard isTitleElement(element), element.text != rule.requiredValue else {
                        return element
                    }
                    return DocumentElement(
                        elementID: element.elementID,
                        kind: element.kind,
                        order: element.order,
                        text: rule.requiredValue,
                        styleID: element.styleID,
                        evidenceIDs: element.evidenceIDs
                    )
                }
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
