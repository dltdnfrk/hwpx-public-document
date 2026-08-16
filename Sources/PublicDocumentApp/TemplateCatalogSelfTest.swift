import CryptoKit
import Foundation

struct TemplateCatalogSelfTestReceipt: Codable {
    let authoritativeTitle: String
    let bootstrappedCatalogVersion: String
    let catalogBoundaryRejections: [String: Bool]
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
        let catalogBoundaryRejections = try boundaryRejections(store: store, key: key)
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
            catalogBoundaryRejections: catalogBoundaryRejections,
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

    private static func boundaryRejections(
        store: TemplateCatalogStore,
        key: Curve25519.Signing.PrivateKey
    ) throws -> [String: Bool] {
        let canonicalPayload = try catalogPayloadData()
        let validEnvelope = try envelopeData(payload: canonicalPayload, key: key)
        guard var envelopeObject = try JSONSerialization.jsonObject(
            with: validEnvelope
        ) as? [String: Any] else {
            throw TemplateCatalogError.invalidEnvelope
        }

        var extraEnvelopeObject = envelopeObject
        extraEnvelopeObject["unexpected"] = true
        var wrongEnvelopeType = envelopeObject
        wrongEnvelopeType["payload"] = 42
        var invalidBase64 = envelopeObject
        invalidBase64["payload"] = "%%%"
        var invalidSignature = envelopeObject
        invalidSignature["signature"] = Data(repeating: 0, count: 64).base64EncodedString()

        let duplicateTemplateID = try mutatedCatalogPayload { catalog in
            var entries = catalog["entries"] as? [[String: Any]] ?? []
            entries[1]["templateID"] = entries[0]["templateID"]
            catalog["entries"] = entries
        }
        let duplicateDocumentType = try mutatedCatalogPayload { catalog in
            var entries = catalog["entries"] as? [[String: Any]] ?? []
            entries[1]["documentType"] = entries[0]["documentType"]
            catalog["entries"] = entries
        }
        let extraCatalogKey = try mutatedCatalogPayload { catalog in
            catalog["unexpected"] = true
        }
        let wrongCatalogType = try mutatedCatalogPayload { catalog in
            catalog["entries"] = "not-an-array"
        }
        let wrongEntryType = try mutatedCatalogPayload { catalog in
            var entries = catalog["entries"] as? [[String: Any]] ?? []
            entries[0]["version"] = 1
            catalog["entries"] = entries
        }
        let wrongStringArrayType = try mutatedCatalogPayload { catalog in
            var entries = catalog["entries"] as? [[String: Any]] ?? []
            entries[0]["requiredSections"] = ["개요", 1]
            catalog["entries"] = entries
        }
        let wrongRuleType = try mutatedCatalogPayload { catalog in
            var entries = catalog["entries"] as? [[String: Any]] ?? []
            var rules = entries[0]["officialRules"] as? [[String: Any]] ?? []
            rules[0]["precedence"] = true
            entries[0]["officialRules"] = rules
            catalog["entries"] = entries
        }
        let extraEntryKey = try mutatedCatalogPayload { catalog in
            var entries = catalog["entries"] as? [[String: Any]] ?? []
            entries[0]["unexpected"] = true
            catalog["entries"] = entries
        }
        let extraRuleKey = try mutatedCatalogPayload { catalog in
            var entries = catalog["entries"] as? [[String: Any]] ?? []
            var rules = entries[0]["officialRules"] as? [[String: Any]] ?? []
            rules[0]["unexpected"] = true
            entries[0]["officialRules"] = rules
            catalog["entries"] = entries
        }
        let noncanonicalPayload = try mutatedCatalogPayload(
            options: [.prettyPrinted, .sortedKeys]
        ) { _ in }

        envelopeObject["payload"] = Data().base64EncodedString()
        envelopeObject["signature"] = try key.signature(for: Data()).base64EncodedString()

        return [
            "emptyFile": rejects(Data(), with: store),
            "oversizedEnvelope": rejects(Data(repeating: 0x20, count: 262_145), with: store),
            "emptyPayload": rejects(try jsonData(envelopeObject), with: store),
            "oversizedPayload": rejects(
                try envelopeData(payload: Data(repeating: 0x61, count: 131_073), key: key),
                with: store
            ),
            "extraEnvelopeKey": rejects(try jsonData(extraEnvelopeObject), with: store),
            "wrongEnvelopeType": rejects(try jsonData(wrongEnvelopeType), with: store),
            "duplicateTemplateID": rejects(
                try envelopeData(payload: duplicateTemplateID, key: key), with: store
            ),
            "duplicateDocumentType": rejects(
                try envelopeData(payload: duplicateDocumentType, key: key), with: store
            ),
            "extraCatalogKey": rejects(
                try envelopeData(payload: extraCatalogKey, key: key), with: store
            ),
            "extraEntryKey": rejects(
                try envelopeData(payload: extraEntryKey, key: key), with: store
            ),
            "extraRuleKey": rejects(
                try envelopeData(payload: extraRuleKey, key: key), with: store
            ),
            "wrongCatalogType": rejects(
                try envelopeData(payload: wrongCatalogType, key: key), with: store
            ),
            "wrongEntryType": rejects(
                try envelopeData(payload: wrongEntryType, key: key), with: store
            ),
            "wrongStringArrayType": rejects(
                try envelopeData(payload: wrongStringArrayType, key: key), with: store
            ),
            "wrongRuleType": rejects(
                try envelopeData(payload: wrongRuleType, key: key), with: store
            ),
            "noncanonicalPayload": rejects(
                try envelopeData(payload: noncanonicalPayload, key: key), with: store
            ),
            "invalidBase64": rejects(try jsonData(invalidBase64), with: store),
            "invalidSignature": rejects(try jsonData(invalidSignature), with: store),
            "truncatedJSON": rejects(Data("{\"keyID\"".utf8), with: store),
            "invalidJSON": rejects(Data("{\"keyID\":}".utf8), with: store),
            "invalidUTF8": rejects(Data([0xff, 0xfe, 0xfd]), with: store),
            "truncatedPayloadJSON": rejects(
                try envelopeData(payload: Data("{\"catalogID\"".utf8), key: key),
                with: store
            ),
            "invalidPayloadJSON": rejects(
                try envelopeData(payload: Data("{\"catalogID\":}".utf8), key: key),
                with: store
            ),
            "invalidPayloadUTF8": rejects(
                try envelopeData(payload: Data([0xff, 0xfe, 0xfd]), key: key),
                with: store
            ),
        ]
    }

    private static func rejects(_ data: Data, with store: TemplateCatalogStore) -> Bool {
        do {
            _ = try store.verifiedCatalog(from: data)
            return false
        } catch TemplateCatalogError.invalidEnvelope {
            return true
        } catch TemplateCatalogError.invalidSignature {
            return true
        } catch {
            return false
        }
    }

    private static func catalogPayloadData() throws -> Data {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        return try encoder.encode(updatedCatalog())
    }

    private static func mutatedCatalogPayload(
        options: JSONSerialization.WritingOptions = [.sortedKeys],
        mutate: (inout [String: Any]) -> Void
    ) throws -> Data {
        guard var catalog = try JSONSerialization.jsonObject(
            with: catalogPayloadData()
        ) as? [String: Any] else {
            throw TemplateCatalogError.invalidEnvelope
        }
        mutate(&catalog)
        return try JSONSerialization.data(withJSONObject: catalog, options: options)
    }

    private static func jsonData(_ object: [String: Any]) throws -> Data {
        try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])
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
            entries: sixEntries(planVersion: "3.2")
        )
    }

    private static func updatedCatalog() -> TemplateCatalogPayload {
        TemplateCatalogPayload(
            catalogID: "public-document-templates",
            version: "2026.09.1",
            publishedAt: "2026-09-01T00:00:00Z",
            entries: sixEntries(planVersion: "3.3", otherVersion: "1.1")
        )
    }

    private static func tamperedCatalog() -> TemplateCatalogPayload {
        TemplateCatalogPayload(
            catalogID: "public-document-templates",
            version: "2026.10.1",
            publishedAt: "2026-10-01T00:00:00Z",
            entries: sixEntries(planVersion: "9.9")
        )
    }

    private static func sixEntries(
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
