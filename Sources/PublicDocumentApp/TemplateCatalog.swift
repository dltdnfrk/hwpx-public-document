import CryptoKit
import CoreFoundation
import Foundation

enum CatalogOfficialField: String, Codable, CaseIterable {
    case title
}

struct CatalogOfficialRule: Codable, Equatable {
    let field: CatalogOfficialField
    let precedence: Int
    let requiredValue: String
    let source: String
}

struct OfficialRuleConflict: Codable, Equatable {
    let field: CatalogOfficialField
    let submittedValue: String
    let requiredValue: String
    let precedence: Int
    let source: String
    let warning: String
}

struct OfficialRuleEnforcementState: Codable, Equatable {
    let appliedRules: [CatalogOfficialRule]
    let conflicts: [OfficialRuleConflict]
    let contentChanged: Bool
}

struct OfficialRuleEnforcement {
    let project: DocumentProject
    let state: OfficialRuleEnforcementState
}

struct TemplateCatalogEntry: Codable, Equatable {
    let templateID: String
    let version: String
    let effectiveDate: String
    let publishingAuthority: String
    let source: String
    let contentHash: String
    let documentType: String
    let requiredSections: [String]
    let checklist: [String]
    let officialRules: [CatalogOfficialRule]
}

struct TemplateCatalogPayload: Codable, Equatable {
    let catalogID: String
    let version: String
    let publishedAt: String
    let entries: [TemplateCatalogEntry]
}

struct TemplateCatalogEnvelope: Codable {
    let keyID: String
    let payload: String
    let signature: String
}

struct TemplateCatalogStatus: Codable {
    let catalogVersion: String
    let publishedAt: String
    let entries: [TemplateCatalogEntry]
    let rollbackAvailable: Bool
}

struct TemplateCatalogHistoryEvent: Codable {
    let catalogVersion: String
    let kind: String
    let recordedAt: String
}

enum TemplateCatalogError: Error, LocalizedError {
    case invalidEnvelope
    case invalidSignature
    case noTrustedCatalog
    case noRollbackCatalog

    var errorDescription: String? {
        switch self {
        case .invalidEnvelope:
            return "템플릿 카탈로그 형식이 올바르지 않습니다."
        case .invalidSignature:
            return "템플릿 카탈로그 서명을 확인할 수 없습니다. 마지막 신뢰 카탈로그를 유지합니다."
        case .noTrustedCatalog:
            return "오프라인에서 사용할 신뢰 템플릿 카탈로그가 없습니다."
        case .noRollbackCatalog:
            return "되돌릴 이전 템플릿 카탈로그가 없습니다."
        }
    }
}

final class TemplateCatalogStore {
    private static let maximumEnvelopeBytes = 262_144
    private static let maximumPayloadBytes = 131_072
    private static let expectedDocumentTypes: Set<String> = [
        "추진계획서", "기안문", "보고서", "결과보고서", "업무협조", "회의록",
    ]

    static let productionPublicKey = Data([
        0xa3, 0xca, 0x24, 0xb7, 0xa4, 0x0d, 0x1b, 0xe0,
        0x62, 0x65, 0x9a, 0x98, 0x95, 0x28, 0x7e, 0x77,
        0x32, 0xe1, 0xcf, 0x8b, 0xbe, 0x7d, 0xe0, 0xe3,
        0xd2, 0x37, 0x83, 0x07, 0x6c, 0x67, 0xf2, 0xce,
    ])

    private let root: URL
    private let publicKey: Curve25519.Signing.PublicKey
    private let bundledEnvelope: Data
    private let fileManager: FileManager
    private let decoder = JSONDecoder()
    private let encoder: JSONEncoder

    init(
        root: URL,
        bundledEnvelope: Data,
        publicKeyData: Data = TemplateCatalogStore.productionPublicKey,
        fileManager: FileManager = .default
    ) throws {
        self.root = root
        self.bundledEnvelope = bundledEnvelope
        self.fileManager = fileManager
        publicKey = try Curve25519.Signing.PublicKey(rawRepresentation: publicKeyData)
        encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
    }

    var trustedEnvelopeFile: URL { root.appendingPathComponent("trusted-catalog.json") }
    var previousEnvelopeFile: URL { root.appendingPathComponent("previous-catalog.json") }
    var historyFile: URL { root.appendingPathComponent("update-history.json") }

    func bootstrap() throws -> TemplateCatalogStatus {
        try fileManager.createDirectory(at: root, withIntermediateDirectories: true)
        if !fileManager.fileExists(atPath: trustedEnvelopeFile.path) {
            let catalog = try verifiedCatalog(from: bundledEnvelope)
            try bundledEnvelope.write(to: trustedEnvelopeFile, options: [.atomic])
            try appendHistory(kind: "bootstrapped", catalog: catalog)
        }
        return try currentStatus()
    }

    func install(_ envelopeData: Data) throws -> TemplateCatalogStatus {
        let catalog = try verifiedCatalog(from: envelopeData)
        try fileManager.createDirectory(at: root, withIntermediateDirectories: true)
        if fileManager.fileExists(atPath: trustedEnvelopeFile.path) {
            let current = try Data(contentsOf: trustedEnvelopeFile)
            try current.write(to: previousEnvelopeFile, options: [.atomic])
        }
        try envelopeData.write(to: trustedEnvelopeFile, options: [.atomic])
        try appendHistory(kind: "installed", catalog: catalog)
        return try currentStatus()
    }

    func rollback() throws -> TemplateCatalogStatus {
        guard fileManager.fileExists(atPath: previousEnvelopeFile.path) else {
            throw TemplateCatalogError.noRollbackCatalog
        }
        let previous = try Data(contentsOf: previousEnvelopeFile)
        let catalog = try verifiedCatalog(from: previous)
        let current = try Data(contentsOf: trustedEnvelopeFile)
        try previous.write(to: trustedEnvelopeFile, options: [.atomic])
        try current.write(to: previousEnvelopeFile, options: [.atomic])
        try appendHistory(kind: "rolled-back", catalog: catalog)
        return try currentStatus()
    }

    func currentStatus() throws -> TemplateCatalogStatus {
        guard fileManager.fileExists(atPath: trustedEnvelopeFile.path) else {
            throw TemplateCatalogError.noTrustedCatalog
        }
        let catalog = try verifiedCatalog(from: Data(contentsOf: trustedEnvelopeFile))
        return TemplateCatalogStatus(
            catalogVersion: catalog.version,
            publishedAt: catalog.publishedAt,
            entries: catalog.entries,
            rollbackAvailable: fileManager.fileExists(atPath: previousEnvelopeFile.path)
        )
    }

    func enforceOfficialRules(in project: DocumentProject) throws -> OfficialRuleEnforcement {
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

    func verifiedCatalog(from envelopeData: Data) throws -> TemplateCatalogPayload {
        guard !envelopeData.isEmpty,
              envelopeData.count <= Self.maximumEnvelopeBytes,
              let envelopeObject = try? jsonObject(from: envelopeData),
              hasExactlyKeys(envelopeObject, ["keyID", "payload", "signature"]),
              let keyID = envelopeObject["keyID"] as? String,
              keyID == "studio-template-root-2026",
              let payloadText = envelopeObject["payload"] as? String,
              let signatureText = envelopeObject["signature"] as? String,
              let payload = canonicalBase64Data(from: payloadText),
              !payload.isEmpty,
              payload.count <= Self.maximumPayloadBytes,
              let signature = canonicalBase64Data(from: signatureText)
        else {
            throw TemplateCatalogError.invalidEnvelope
        }
        guard publicKey.isValidSignature(signature, for: payload) else {
            throw TemplateCatalogError.invalidSignature
        }
        guard let catalogObject = try? jsonObject(from: payload),
              isValidCatalogObject(catalogObject),
              let canonicalPayload = try? JSONSerialization.data(
                  withJSONObject: catalogObject,
                  options: [.sortedKeys, .withoutEscapingSlashes]
              ),
              canonicalPayload == payload,
              let catalog = try? decoder.decode(TemplateCatalogPayload.self, from: payload)
        else {
            throw TemplateCatalogError.invalidEnvelope
        }
        return catalog
    }

    private func jsonObject(from data: Data) throws -> [String: Any] {
        guard let object = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw TemplateCatalogError.invalidEnvelope
        }
        return object
    }

    private func canonicalBase64Data(from text: String) -> Data? {
        guard let data = Data(base64Encoded: text), data.base64EncodedString() == text else {
            return nil
        }
        return data
    }

    private func hasExactlyKeys(_ object: [String: Any], _ keys: Set<String>) -> Bool {
        Set(object.keys) == keys
    }

    private func isValidCatalogObject(_ catalog: [String: Any]) -> Bool {
        guard hasExactlyKeys(catalog, ["catalogID", "version", "publishedAt", "entries"]),
              catalog["catalogID"] as? String == "public-document-templates",
              catalog["version"] is String,
              catalog["publishedAt"] is String,
              let entries = catalog["entries"] as? [[String: Any]],
              entries.count == Self.expectedDocumentTypes.count,
              entries.allSatisfy(isValidCatalogEntry)
        else {
            return false
        }

        let templateIDs = entries.compactMap { $0["templateID"] as? String }
        let documentTypes = entries.compactMap { $0["documentType"] as? String }
        return Set(templateIDs).count == entries.count
            && Set(documentTypes) == Self.expectedDocumentTypes
    }

    private func isValidCatalogEntry(_ entry: [String: Any]) -> Bool {
        let keys: Set<String> = [
            "templateID", "version", "effectiveDate", "publishingAuthority", "source",
            "documentType", "requiredSections", "checklist", "officialRules", "contentHash",
        ]
        guard hasExactlyKeys(entry, keys),
              entry["templateID"] is String,
              entry["version"] is String,
              entry["effectiveDate"] is String,
              entry["publishingAuthority"] is String,
              entry["source"] is String,
              entry["documentType"] is String,
              entry["contentHash"] is String,
              isStringArray(entry["requiredSections"]),
              isStringArray(entry["checklist"]),
              let rules = entry["officialRules"] as? [[String: Any]]
        else {
            return false
        }
        return rules.allSatisfy(isValidOfficialRule)
    }

    private func isValidOfficialRule(_ rule: [String: Any]) -> Bool {
        hasExactlyKeys(rule, ["field", "precedence", "requiredValue", "source"])
            && rule["field"] is String
            && isJSONInteger(rule["precedence"])
            && rule["requiredValue"] is String
            && rule["source"] is String
    }

    private func isStringArray(_ value: Any?) -> Bool {
        guard let values = value as? [Any] else { return false }
        return values.allSatisfy { $0 is String }
    }

    private func isJSONInteger(_ value: Any?) -> Bool {
        guard let number = value as? NSNumber,
              CFGetTypeID(number) != CFBooleanGetTypeID()
        else {
            return false
        }
        let value = number.doubleValue
        return value.isFinite && value.rounded(.towardZero) == value
    }

    private func appendHistory(kind: String, catalog: TemplateCatalogPayload) throws {
        let existing = (try? decoder.decode(
            [TemplateCatalogHistoryEvent].self,
            from: Data(contentsOf: historyFile)
        )) ?? []
        let event = TemplateCatalogHistoryEvent(
            catalogVersion: catalog.version,
            kind: kind,
            recordedAt: ISO8601DateFormatter().string(from: Date())
        )
        try encoder.encode(existing + [event]).write(to: historyFile, options: [.atomic])
    }

    private func highestPrecedenceRules(
        in entries: [TemplateCatalogEntry],
        templateID: String
    ) -> [CatalogOfficialRule] {
        var selected: [CatalogOfficialField: CatalogOfficialRule] = [:]
        let candidates = entries
            .filter { $0.templateID == templateID }
            .flatMap(\.officialRules)
        for rule in candidates {
            guard let current = selected[rule.field] else {
                selected[rule.field] = rule
                continue
            }
            if rule.precedence > current.precedence {
                selected[rule.field] = rule
            }
        }
        return CatalogOfficialField.allCases.compactMap { selected[$0] }
    }

    private func isTitleElement(_ element: DocumentElement) -> Bool {
        element.elementID == "element-title" || element.styleID == "style-title"
    }
}
