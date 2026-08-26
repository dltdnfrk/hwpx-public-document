import CryptoKit
import Foundation

extension TemplateCatalogSelfTest {
    static func boundaryRejections(
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

    static func rejects(_ data: Data, with store: TemplateCatalogStore) -> Bool {
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

    static func catalogPayloadData() throws -> Data {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        return try encoder.encode(updatedCatalog())
    }

    static func mutatedCatalogPayload(
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

    static func jsonData(_ object: [String: Any]) throws -> Data {
        try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])
    }
}
