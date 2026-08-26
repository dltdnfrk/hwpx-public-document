import Foundation

extension TemplateCatalogStore {
    func officialRuleEnforcement(in project: DocumentProject) throws -> OfficialRuleEnforcement {
        let rules = highestPrecedenceRules(
            in: try currentStatus().entries,
            templateID: project.templateBinding.templateID
        )
        var authoritativeTitle = project.title
        var authoritativeElements = project.elements
        var conflicts: [OfficialRuleConflict] = []

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
            }
        }

        guard authoritativeTitle != project.title || authoritativeElements != project.elements else {
            return OfficialRuleEnforcement(
                project: project,
                state: OfficialRuleEnforcementState(
                    appliedRules: rules,
                    conflicts: conflicts,
                    contentChanged: false
                )
            )
        }

        let createdAt = ISO8601DateFormatter().string(from: Date())
        let revisionID = "revision-official-rule-\(UUID().uuidString.lowercased())"
        let revision = DocumentRevision(
            revisionID: revisionID,
            parentRevisionID: project.currentRevisionID,
            createdAt: createdAt,
            summary: "official-rule-enforced:title",
            elementIDs: authoritativeElements.map(\.elementID),
            snapshotElements: authoritativeElements
        )
        let historyEvent = ProjectHistoryEvent(
            eventID: "history-official-rule-\(UUID().uuidString.lowercased())",
            kind: "official-rule-enforced:title",
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
                contentChanged: true
            )
        )
    }
}
