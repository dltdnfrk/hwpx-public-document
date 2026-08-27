import CryptoKit
import Foundation

enum CatalogOfficialField: String, Codable, CaseIterable {
    case title
    case endMark
    case attachment
    case senderName
}

final class TemplateCatalogStore {
    private static let maximumEnvelopeBytes = 262_144
    private static let maximumPayloadBytes = 131_072
    static let expectedDocumentTypes: Set<String> = [
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
        try officialRuleEnforcement(in: project)
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

    func appendHistory(kind: String, catalog: TemplateCatalogPayload) throws {
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

    func highestPrecedenceRules(
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

    func isTitleElement(_ element: DocumentElement) -> Bool {
        element.elementID == "element-title" || element.styleID == "style-title"
    }
}
