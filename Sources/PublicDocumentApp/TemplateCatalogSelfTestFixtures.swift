import CryptoKit
import Foundation

extension TemplateCatalogSelfTest {
    static func conflictingProject(
        binding: ProjectTemplateBinding
    ) -> DocumentProject {
        let title = "템플릿 제안 제목"
        let titleElement = DocumentElement(
            elementID: "element-title",
            kind: "heading",
            order: 0,
            text: title,
            contentHTML: title,
            inlineIDs: [],
            styleID: "style-title",
            evidenceIDs: []
        )
        let revision = DocumentRevision(
            revisionID: "revision-template-title",
            createdAt: "2026-09-01T00:00:00Z",
            summary: "template-title-applied",
            elementIDs: [titleElement.elementID],
            snapshotElements: [titleElement]
        )
        return DocumentProject(
            schemaVersion: DocumentProjectStore.currentSchemaVersion,
            documentID: "document-official-rule",
            locale: "ko-KR",
            title: title,
            currentRevisionID: revision.revisionID,
            elements: [titleElement],
            assets: [],
            styles: [DocumentStyle(
                styleID: "style-title",
                name: "문서 제목",
                properties: ["level": "1"]
            )],
            templateBinding: binding,
            evidenceLinks: [],
            revisions: [revision],
            history: [ProjectHistoryEvent(
                eventID: "history-template-title",
                kind: "template-title-applied",
                revisionID: revision.revisionID,
                createdAt: revision.createdAt
            )],
            aiProposalHistory: []
        )
    }

    static func unsupportedOfficialFieldEnvelope(
        key: Curve25519.Signing.PrivateKey
    ) throws -> Data {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        let encoded = try encoder.encode(updatedCatalog())
        guard var payload = try JSONSerialization.jsonObject(with: encoded) as? [String: Any],
              var entries = payload["entries"] as? [[String: Any]],
              !entries.isEmpty
        else { throw TemplateCatalogError.invalidEnvelope }
        var first = entries[0]
        var rules = first["officialRules"] as? [[String: Any]] ?? []
        rules.append([
            "field": "unsupported-official-field",
            "precedence": 1_000,
            "requiredValue": "지원할 수 없는 값",
            "source": "지원되지 않는 규칙",
        ])
        first["officialRules"] = rules
        entries[0] = first
        payload["entries"] = entries
        let rawPayload = try JSONSerialization.data(
            withJSONObject: payload,
            options: [.sortedKeys]
        )
        return try envelopeData(payload: rawPayload, key: key)
    }

    static func envelopeData(
        for catalog: TemplateCatalogPayload,
        key: Curve25519.Signing.PrivateKey
    ) throws -> Data {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        let payload = try encoder.encode(catalog)
        return try envelopeData(payload: payload, key: key)
    }

    static func envelopeData(
        payload: Data,
        key: Curve25519.Signing.PrivateKey
    ) throws -> Data {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        let envelope = TemplateCatalogEnvelope(
            keyID: "studio-template-root-2026",
            payload: payload.base64EncodedString(),
            signature: try key.signature(for: payload).base64EncodedString()
        )
        return try encoder.encode(envelope)
    }

    static func initialCatalog() -> TemplateCatalogPayload {
        TemplateCatalogPayload(
            catalogID: "public-document-templates",
            version: "2026.08.1",
            publishedAt: "2026-08-01T00:00:00Z",
            entries: sixEntries(planVersion: "3.2")
        )
    }

    static func updatedCatalog() -> TemplateCatalogPayload {
        TemplateCatalogPayload(
            catalogID: "public-document-templates",
            version: "2026.09.1",
            publishedAt: "2026-09-01T00:00:00Z",
            entries: sixEntries(planVersion: "3.3", otherVersion: "1.1")
        )
    }

    static func tamperedCatalog() -> TemplateCatalogPayload {
        TemplateCatalogPayload(
            catalogID: "public-document-templates",
            version: "2026.10.1",
            publishedAt: "2026-10-01T00:00:00Z",
            entries: sixEntries(planVersion: "9.9")
        )
    }

    static func sixEntries(
        planVersion: String,
        otherVersion: String = "1.0"
    ) -> [TemplateCatalogEntry] {
        [
            entry(version: planVersion, documentType: "추진계획서"),
            entry(version: otherVersion, documentType: "기안문", templateID: "public-draft"),
            entry(version: otherVersion, documentType: "보고서", templateID: "public-report"),
            entry(version: otherVersion, documentType: "결과보고서", templateID: "public-result"),
            entry(version: otherVersion, documentType: "업무협조", templateID: "public-cooperation"),
            entry(version: otherVersion, documentType: "회의록", templateID: "public-minutes"),
        ]
    }

    static func entry(
        version: String,
        documentType: String,
        templateID: String = "public-plan"
    ) -> TemplateCatalogEntry {
        TemplateCatalogEntry(
            templateID: templateID,
            version: version,
            effectiveDate: "2026-08-01",
            publishingAuthority: "기관 표준",
            source: "기관 표준",
            contentHash: "sha256:fixture-\(templateID)-\(version)",
            documentType: documentType,
            requiredSections: ["개요", "추진 배경", "세부 추진계획", "예산 및 일정", "검토 및 결재"],
            checklist: ["목적과 대상", "추진 근거", "담당 부서", "시행 일정", "소요 예산", "결재선"],
            officialRules: [
                CatalogOfficialRule(
                    field: .title,
                    precedence: 10,
                    requiredValue: "하위 우선순위 제목",
                    source: "기관 템플릿 기본값"
                ),
                CatalogOfficialRule(
                    field: .title,
                    precedence: 100,
                    requiredValue: "기관 공식 제목을 사용하세요",
                    source: "기관 표준"
                ),
            ]
        )
    }
}
