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
}
