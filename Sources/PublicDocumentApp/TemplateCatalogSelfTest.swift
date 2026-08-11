import CryptoKit
import Foundation

struct TemplateCatalogSelfTestReceipt: Codable {
    let authoritativeTitle: String
    let bootstrappedCatalogVersion: String
    let conflictWarning: String
    let exportBoundProjectTitle: String
    let exportSnapshotUsedRuleRevision: Bool
    let failedUpdatePreservedLastTrusted: Bool
    let highestAppliedPrecedence: Int
    let immutableRevisionCreated: Bool
    let lowerPrecedenceCouldNotOverride: Bool
    let offlineReloadCatalogVersion: String
    let officialRuleHistoryRecorded: Bool
    let officialRuleTitleElementEnforced: Bool
    let pinnedTemplateVersionAfterUpdate: String
    let pinnedTemplateVersionBeforeUpdate: String
    let repeatedEnforcementWasIdempotent: Bool
    let rollbackCatalogVersion: String
    let signatureRejected: Bool
    let unsupportedOfficialFieldRejected: Bool
    let updatedCatalogEntryCount: Int
    let updatedCatalogVersion: String
}

enum TemplateCatalogSelfTest {
    static func run(at root: URL) throws -> TemplateCatalogSelfTestReceipt {
        let key = Curve25519.Signing.PrivateKey()
        let initialEnvelope = try envelopeData(for: initialCatalog(), key: key)
        let store = try TemplateCatalogStore(
            root: root,
            bundledEnvelope: initialEnvelope,
            publicKeyData: key.publicKey.rawRepresentation
        )
        let pinnedBinding = ProjectTemplateBinding(
            templateID: "public-plan",
            version: "3.2",
            publishingAuthority: "기관 표준",
            requiredSections: ["개요", "추진 배경"],
            checklistResults: ["목적과 대상": true]
        )
        let initial = try store.bootstrap()
        let updated = try store.install(envelopeData(for: updatedCatalog(), key: key))
        let submitted = conflictingProject(binding: pinnedBinding)
        let enforcement = try store.enforceOfficialRules(in: submitted)
        let repeated = try store.enforceOfficialRules(in: enforcement.project)
        let exportRoot = root.appendingPathComponent("official-rule-export", isDirectory: true)
        let exportReceipt = try DocumentExportEngine().export(
            project: enforcement.project,
            request: ExportRequest(
                operationID: "official-rule-export",
                destination: exportRoot,
                formats: [.markdown],
                flatteningConsent: []
            )
        )
        let markdown = try String(
            contentsOf: exportRoot.appendingPathComponent("ac05-fixture.md"),
            encoding: .utf8
        )
        let exportBoundProjectTitle = markdown
            .components(separatedBy: .newlines)
            .first { $0.hasPrefix("# ") } ?? ""
        var unsupportedOfficialFieldRejected = false
        do {
            _ = try store.install(unsupportedOfficialFieldEnvelope(key: key))
        } catch TemplateCatalogError.invalidEnvelope {
            unsupportedOfficialFieldRejected = true
        }
        var signatureRejected = false
        var tamperedEnvelope = try JSONDecoder().decode(
            TemplateCatalogEnvelope.self,
            from: envelopeData(for: tamperedCatalog(), key: key)
        )
        tamperedEnvelope = TemplateCatalogEnvelope(
            keyID: tamperedEnvelope.keyID,
            payload: tamperedEnvelope.payload.replacingOccurrences(of: "A", with: "B"),
            signature: tamperedEnvelope.signature
        )
        do {
            _ = try store.install(JSONEncoder().encode(tamperedEnvelope))
        } catch TemplateCatalogError.invalidSignature {
            signatureRejected = true
        } catch TemplateCatalogError.invalidEnvelope {
            signatureRejected = true
        }
        let afterFailure = try store.currentStatus()
        let offlineStore = try TemplateCatalogStore(
            root: root,
            bundledEnvelope: initialEnvelope,
            publicKeyData: key.publicKey.rawRepresentation
        )
        let offline = try offlineStore.bootstrap()
        let rolledBack = try offlineStore.rollback()
        let appliedRule = enforcement.state.appliedRules.first {
            $0.field == CatalogOfficialField.title
        }
        let conflict = enforcement.state.conflicts.first {
            $0.field == CatalogOfficialField.title
        }
        let titleElement = enforcement.project.elements.first {
            $0.elementID == "element-title" || $0.styleID == "style-title"
        }
        let createdRevision = enforcement.project.revisions.last
        let exportSnapshotUsedRuleRevision = exportReceipt.snapshotRevisionID
            == enforcement.project.currentRevisionID
        let immutableRevisionCreated = enforcement.project.revisions.count
            == submitted.revisions.count + 1
            && enforcement.project.revisions.first == submitted.revisions.first
            && createdRevision?.parentRevisionID == submitted.currentRevisionID
            && createdRevision?.snapshotElements == enforcement.project.elements
        let officialRuleHistoryRecorded = enforcement.project.history.last?.kind
            == "official-rule-enforced:title"
            && enforcement.project.history.last?.revisionID
                == enforcement.project.currentRevisionID
        let repeatedEnforcementWasIdempotent = repeated.project == enforcement.project
            && !repeated.state.contentChanged
            && repeated.state.conflicts.isEmpty
        return TemplateCatalogSelfTestReceipt(
            authoritativeTitle: enforcement.project.title,
            bootstrappedCatalogVersion: initial.catalogVersion,
            conflictWarning: conflict?.warning ?? "",
            exportBoundProjectTitle: exportBoundProjectTitle,
            exportSnapshotUsedRuleRevision: exportSnapshotUsedRuleRevision,
            failedUpdatePreservedLastTrusted: afterFailure.catalogVersion == updated.catalogVersion,
            highestAppliedPrecedence: appliedRule?.precedence ?? -1,
            immutableRevisionCreated: immutableRevisionCreated,
            lowerPrecedenceCouldNotOverride: enforcement.project.title
                != "하위 우선순위 제목",
            offlineReloadCatalogVersion: offline.catalogVersion,
            officialRuleHistoryRecorded: officialRuleHistoryRecorded,
            officialRuleTitleElementEnforced: titleElement?.text == enforcement.project.title,
            pinnedTemplateVersionAfterUpdate: enforcement.project.templateBinding.version,
            pinnedTemplateVersionBeforeUpdate: pinnedBinding.version,
            repeatedEnforcementWasIdempotent: repeatedEnforcementWasIdempotent,
            rollbackCatalogVersion: rolledBack.catalogVersion,
            signatureRejected: signatureRejected,
            unsupportedOfficialFieldRejected: unsupportedOfficialFieldRejected,
            updatedCatalogEntryCount: updated.entries.count,
            updatedCatalogVersion: updated.catalogVersion
        )
    }

    private static func conflictingProject(
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

    private static func unsupportedOfficialFieldEnvelope(
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

    private static func envelopeData(
        for catalog: TemplateCatalogPayload,
        key: Curve25519.Signing.PrivateKey
    ) throws -> Data {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        let payload = try encoder.encode(catalog)
        return try envelopeData(payload: payload, key: key)
    }

    private static func envelopeData(
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

    private static func initialCatalog() -> TemplateCatalogPayload {
        TemplateCatalogPayload(
            catalogID: "public-document-templates",
            version: "2026.08.1",
            publishedAt: "2026-08-01T00:00:00Z",
            entries: [entry(version: "3.2", documentType: "추진계획서")]
        )
    }

    private static func updatedCatalog() -> TemplateCatalogPayload {
        TemplateCatalogPayload(
            catalogID: "public-document-templates",
            version: "2026.09.1",
            publishedAt: "2026-09-01T00:00:00Z",
            entries: [
                entry(version: "3.3", documentType: "추진계획서"),
                entry(version: "1.0", documentType: "결과보고서", templateID: "public-result"),
            ]
        )
    }

    private static func tamperedCatalog() -> TemplateCatalogPayload {
        TemplateCatalogPayload(
            catalogID: "public-document-templates",
            version: "2026.10.1",
            publishedAt: "2026-10-01T00:00:00Z",
            entries: [entry(version: "9.9", documentType: "위조 템플릿")]
        )
    }

    private static func entry(
        version: String,
        documentType: String,
        templateID: String = "public-plan"
    ) -> TemplateCatalogEntry {
        TemplateCatalogEntry(
            templateID: templateID,
            version: version,
            effectiveDate: "2026-08-01",
            publishingAuthority: "기관 표준",
            source: "공공문서 작성 지침",
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
                    source: "공공문서 작성 지침 제4조"
                ),
            ]
        )
    }
}
