import CoreFoundation
import Foundation

extension TemplateCatalogStore {
    func jsonObject(from data: Data) throws -> [String: Any] {
        guard let object = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw TemplateCatalogError.invalidEnvelope
        }
        return object
    }

    func canonicalBase64Data(from text: String) -> Data? {
        guard let data = Data(base64Encoded: text), data.base64EncodedString() == text else {
            return nil
        }
        return data
    }

    func hasExactlyKeys(_ object: [String: Any], _ keys: Set<String>) -> Bool {
        Set(object.keys) == keys
    }

    func isValidCatalogObject(_ catalog: [String: Any]) -> Bool {
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

    func isValidCatalogEntry(_ entry: [String: Any]) -> Bool {
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

    func isValidOfficialRule(_ rule: [String: Any]) -> Bool {
        guard hasExactlyKeys(rule, ["field", "precedence", "requiredValue", "source"]),
              let field = rule["field"] as? String,
              CatalogOfficialField(rawValue: field) != nil,
              isJSONInteger(rule["precedence"]),
              rule["requiredValue"] is String,
              rule["source"] is String
        else {
            return false
        }
        return true
    }

    func isStringArray(_ value: Any?) -> Bool {
        guard let values = value as? [Any] else { return false }
        return values.allSatisfy { $0 is String }
    }

    func isJSONInteger(_ value: Any?) -> Bool {
        guard let number = value as? NSNumber,
              CFGetTypeID(number) != CFBooleanGetTypeID()
        else {
            return false
        }
        let value = number.doubleValue
        return value.isFinite && value.rounded(.towardZero) == value
    }
}
