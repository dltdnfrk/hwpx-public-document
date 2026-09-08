import CryptoKit
import Foundation
import LocalAuthentication
import Security

// Compile the production engines, not behavioral substitutes. All artifacts are retained.
struct FormatCapabilityResource: Decodable {
    let manifestVersion: String
    let matrix: [FormatCapabilityRow]
}

struct FormatCapabilityRow: Decodable {
    let capability: String
    let hwpx: String
    let hwp: String
    let docx: String
    let markdown: String

    func classification(for format: DocumentFormat) -> String {
        switch format {
        case .hwpx: return hwpx
        case .hwp: return hwp
        case .docx: return docx
        case .markdown: return markdown
        }
    }
}

@main
struct NativeIntegrityRegression {
    static let encoder: JSONEncoder = {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
        return encoder
    }()

    static func project(_ input: URL) throws -> DocumentProject {
        try JSONDecoder().decode(DocumentProject.self, from: Data(contentsOf: input))
    }

    static func emit<T: Encodable>(_ value: T) throws {
        FileHandle.standardOutput.write(try encoder.encode(value))
    }

    static func main() throws {
        let mode = CommandLine.arguments[1]
        let input = URL(fileURLWithPath: CommandLine.arguments[2])
        let output = URL(fileURLWithPath: CommandLine.arguments[3], isDirectory: true)
        try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
        let original = try project(input)
        switch mode {
        case "settings-present", "settings-missing", "settings-denied", "settings-credential":
            let settingsRoot = output.appendingPathComponent("settings")
            try FileManager.default.createDirectory(at: settingsRoot, withIntermediateDirectories: true)
            let setting = AIProviderSetting(provider: "openai", endpointIdentity: "https://api.openai.com/v1", model: "fixture-model", keychainAccountReference: "fixture-account")
            let settingsFile = AISettingsFile(schemaVersion: 1, activeProvider: "openai", providers: ["openai": setting])
            let settingsData = try encoder.encode(settingsFile)
            let settingsURL = settingsRoot.appendingPathComponent("ai-settings.json")
            try settingsData.write(to: settingsURL, options: .withoutOverwriting)
            var dataQueries = 0
            var metadataQueries = 0
            var noninteractive = true
            var identityMatched = true
            var metadataOnly = true
            let credentials = AIKeychainCredentialStore(service: "fixture-service") { query, result in
                let values = query as NSDictionary
                let context = values[kSecUseAuthenticationContext] as? LAContext
                noninteractive = noninteractive && (context?.interactionNotAllowed == true
                    || values[kSecUseAuthenticationUI] as? String == kSecUseAuthenticationUIFail as String)
                identityMatched = identityMatched && values[kSecAttrService] as? String == "fixture-service"
                    && values[kSecAttrAccount] as? String == "fixture-account"
                    && values[kSecClass] as? String == kSecClassGenericPassword as String
                    && values[kSecMatchLimit] as? String == kSecMatchLimitOne as String
                if values[kSecReturnData] as? Bool == true {
                    dataQueries += 1
                    if mode == "settings-credential" {
                        result?.pointee = Data("fixture-secret-sentinel".utf8) as CFData
                        return errSecSuccess
                    }
                    // A protected existing item refuses decryption; existence does not.
                    return errSecInteractionNotAllowed
                }
                metadataQueries += 1
                metadataOnly = metadataOnly && values[kSecReturnAttributes] as? Bool == true
                    && values[kSecReturnData] as? Bool == false && result == nil
                    && context?.interactionNotAllowed == true
                return mode == "settings-missing" ? errSecItemNotFound
                    : mode == "settings-denied" ? errSecInteractionNotAllowed : errSecSuccess
            }
            let settings = AISettingsStore(root: settingsRoot, credentials: credentials)
            if mode == "settings-credential" {
                try emit(["credentialRetrieved": settings.credential(for: setting) == "fixture-secret-sentinel"])
            } else {
                let response = AIBridgeCLI.run(input: Data("{\"action\":\"loadAISettings\"}".utf8), settings: settings)
                try response.write(to: output.appendingPathComponent("bridge-response.json"), options: .withoutOverwriting)
                FileHandle.standardOutput.write(response)
            }
            let audit: [String: Any] = [
                "dataQueries": dataQueries, "metadataQueries": metadataQueries,
                "noninteractive": noninteractive, "identityMatched": identityMatched, "metadataOnly": metadataOnly,
                "settingsPreserved": try Data(contentsOf: settingsURL) == settingsData,
            ]
            try JSONSerialization.data(withJSONObject: audit, options: [.sortedKeys])
                .write(to: output.appendingPathComponent("query-audit.json"), options: .withoutOverwriting)
        case "batch":
            let store = BatchExportStore(fileManager: .default)
            let root = store.operationRoot(for: output, operationID: "operation")
            try store.prepare(root)
            let request = BatchExportRequest(
                operationID: "operation", retryOfOperationID: nil, destination: output,
                documents: [BatchDocumentInput(project: original, fileStem: "safe")],
                formats: [.markdown], flatteningConsent: []
            )
            do {
                let manifest = try store.initialManifest(request: request, operationRoot: root, selectedFormats: [.markdown])
                try store.persist(manifest, at: root)
                let retry = try store.retryRequest(destination: output, previousOperationID: "operation", newOperationID: "retry")
                try emit([
                    "rejected": false,
                    "retryEqual": retry.documents.first?.project == original,
                    "stagingConfined": store.itemStagingRoot(root, itemID: manifest.items[0].itemID)
                        .deletingLastPathComponent().resolvingSymlinksInPath().path == store.stagingRoot(root).resolvingSymlinksInPath().path,
                ])
            } catch is BatchExportError {
                try emit(["rejected": true])
            }
        case "retry":
            let store = BatchExportStore(fileManager: .default)
            do {
                _ = try store.retryRequest(destination: output, previousOperationID: "operation", newOperationID: "retry")
                try emit(["rejected": false])
            } catch is BatchExportError {
                try emit(["rejected": true])
            }
        case "ai":
            var current = original
            var rejected = false
            do {
                current = try AIGovernanceEngine().approve(proposalID: "proposal", commandIDs: nil, in: original)
            } catch AIGovernanceError.invalidProposal {
                rejected = true
            }
            try encoder.encode(current).write(to: output.appendingPathComponent("project.json"), options: .withoutOverwriting)
            var undoEqual = false
            var redoEqual = false
            if !rejected {
                let undone = try AIGovernanceEngine().undo(in: current)
                undoEqual = undone.elements == original.elements
                redoEqual = try AIGovernanceEngine().redo(in: undone).elements == current.elements
            }
            try emit(["rejected": rejected, "originalPreserved": current == original, "undoEqual": undoEqual, "redoEqual": redoEqual])
        case "title":
            let required = "Required & title"
            let entries = TemplateCatalogStore.expectedDocumentTypes.sorted().enumerated().map { index, type in
                TemplateCatalogEntry(
                    templateID: index == 0 ? original.templateBinding.templateID : "template-\(index)",
                    version: "1", effectiveDate: "2026-09-05", publishingAuthority: "fixture", source: "fixture",
                    contentHash: "sha256:fixture", documentType: type, requiredSections: [], checklist: [],
                    officialRules: [CatalogOfficialRule(field: .title, precedence: 100, requiredValue: required, source: "fixture")]
                )
            }
            let payload = try encoder.encode(TemplateCatalogPayload(
                catalogID: "public-document-templates", version: "1", publishedAt: "2026-09-05T00:00:00Z", entries: entries
            ))
            let key = try Curve25519.Signing.PrivateKey(rawRepresentation: Data(repeating: 7, count: 32))
            let envelope = try encoder.encode(TemplateCatalogEnvelope(
                keyID: "studio-template-root-2026", payload: payload.base64EncodedString(),
                signature: key.signature(for: payload).base64EncodedString()
            ))
            let store = try TemplateCatalogStore(root: output.appendingPathComponent("catalog"), bundledEnvelope: envelope, publicKeyData: key.publicKey.rawRepresentation)
            _ = try store.bootstrap()
            let result = try store.enforceOfficialRules(in: original)
            try encoder.encode(result.project).write(to: output.appendingPathComponent("project.json"), options: .withoutOverwriting)
            try ExportSerializers.docx(project: result.project).write(to: output.appendingPathComponent("document.docx"), options: .withoutOverwriting)
            let again = try store.enforceOfficialRules(in: result.project)
            try emit(["idempotent": again.project == result.project, "changed": result.state.contentChanged])
        case "docx":
            try ExportSerializers.docx(project: original).write(to: output.appendingPathComponent("document.docx"), options: .withoutOverwriting)
            try emit(["written": true])
        case "export":
            let receipt = try DocumentExportEngine().export(project: original, request: ExportRequest(
                operationID: "integrity-export", destination: output, formats: [.markdown], flatteningConsent: [.markdown]
            ))
            try emit(receipt)
        default:
            throw ExportError.invalidPackage("unknown fixture mode")
        }
    }
}
