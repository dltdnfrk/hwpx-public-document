import Foundation

enum OfficialRuleSkeleton {
    static func apply(
        rule: CatalogOfficialRule,
        to project: DocumentProject
    ) -> (elements: [DocumentElement], conflict: OfficialRuleConflict)? {
        var elements = project.elements
        switch rule.field {
        case .endMark:
            guard !hasEndMark(elements) else { return nil }
            elements.append(marker(id: "element-end-mark", text: rule.requiredValue, styleID: "style-end-mark", order: nextOrder(elements)))
        case .attachment:
            guard hasAttachments(project), !hasAttachmentLabel(elements) else { return nil }
            elements.append(marker(id: "element-attachment", text: rule.requiredValue, styleID: "style-attachment", order: nextOrder(elements)))
        case .senderName:
            guard !isInternalApproval(elements), !hasSenderName(elements) else { return nil }
            elements.append(marker(id: "element-sender-name", text: rule.requiredValue, styleID: "style-sender-name", order: nextOrder(elements)))
        case .title:
            return nil
        }
        return (elements, OfficialRuleConflict(
            field: rule.field,
            submittedValue: "",
            requiredValue: rule.requiredValue,
            precedence: rule.precedence,
            source: rule.source,
            warning: "공식 규칙 충돌: 제출 본문에 「\(rule.requiredValue)」가 없어 공식 규칙(우선순위 \(rule.precedence))의 필수 표기를 적용했습니다: '\(rule.requiredValue)'."
        ))
    }

    static func hasEndMark(_ elements: [DocumentElement]) -> Bool {
        elements.contains {
            $0.styleID == "style-end-mark"
                || $0.text.trimmingCharacters(in: .whitespacesAndNewlines) == "끝"
                || $0.text.hasSuffix(" 끝")
        }
    }

    static func hasAttachments(_ project: DocumentProject) -> Bool {
        !project.assets.isEmpty || project.elements.contains {
            $0.kind == "attachment" || $0.styleID == "style-attachment"
        }
    }

    static func hasAttachmentLabel(_ elements: [DocumentElement]) -> Bool {
        elements.contains {
            $0.styleID == "style-attachment"
                || $0.text.trimmingCharacters(in: .whitespacesAndNewlines) == "붙임"
                || $0.text.hasPrefix("붙임")
        }
    }

    static func isInternalApproval(_ elements: [DocumentElement]) -> Bool {
        elements.contains { $0.styleID == "style-internal-approval" || $0.text.contains("내부결재") }
    }

    static func hasSenderName(_ elements: [DocumentElement]) -> Bool {
        elements.contains {
            $0.styleID == "style-sender-name"
                || $0.text.trimmingCharacters(in: .whitespacesAndNewlines) == "발신명의"
                || $0.text.hasPrefix("발신명의")
        }
    }

    private static func nextOrder(_ elements: [DocumentElement]) -> Int {
        (elements.map(\.order).max() ?? -1) + 1
    }

    private static func marker(id: String, text: String, styleID: String, order: Int) -> DocumentElement {
        DocumentElement(
            elementID: id,
            kind: "paragraph",
            order: order,
            text: text,
            contentHTML: text,
            styleID: styleID,
            evidenceIDs: []
        )
    }
}
