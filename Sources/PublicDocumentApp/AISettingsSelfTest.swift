import Darwin
import Foundation

struct AISettingsSelfTestReceipt: Codable {
    let modelPersisted: Bool
    let modelUsedByTransport: Bool
    let secretAbsentFromSettingsFile: Bool
    let snapshotReportsStoredSecret: Bool
    let deleteRemovedSetting: Bool
    let deleteRemovedCredential: Bool
}

enum AISettingsSelfTest {
    static func run(at root: URL) throws -> AISettingsSelfTestReceipt {
        let service = "com.muni.public-document.ai-settings-self-test.\(UUID().uuidString)"
        setenv("PUBLIC_DOCUMENT_STUDIO_AI_KEYCHAIN_SERVICE", service, 1)
        defer { unsetenv("PUBLIC_DOCUMENT_STUDIO_AI_KEYCHAIN_SERVICE") }
        let provider = AIProviderKind.openAICompatible
        let store = AISettingsStore(root: root)
        let secret = "AI-SETTINGS-SELF-TEST-SECRET"
        let setting = try store.save(
            provider: provider,
            endpointIdentity: "http://127.0.0.1:18999/v1",
            model: "audit-model",
            secret: secret
        )
        defer { try? AIKeychainCredentialStore(service: service).delete(accountReference: setting.keychainAccountReference) }
        let snapshot = try store.snapshot()
        let request = try AIProviderTransport().makeRequest(
            binding: AIRequestBinding(
                documentID: "settings-self-test",
                provider: provider,
                endpointIdentity: setting.endpointIdentity,
                model: setting.model,
                operation: .summarize,
                payloadScope: "whole-document"
            ),
            instruction: "test",
            elements: [],
            credential: secret
        )
        let body = try request.httpBody.map {
            try JSONSerialization.jsonObject(with: $0) as? [String: Any]
        } ?? nil
        let settingsText = try String(
            contentsOf: root.appendingPathComponent("ai-settings.json"),
            encoding: .utf8
        )
        try store.delete(provider: provider)
        let credentialMissing: Bool
        do {
            _ = try AIKeychainCredentialStore(service: service).get(
                accountReference: setting.keychainAccountReference
            )
            credentialMissing = false
        } catch {
            credentialMissing = true
        }
        return AISettingsSelfTestReceipt(
            modelPersisted: setting.model == "audit-model",
            modelUsedByTransport: body?["model"] as? String == "audit-model",
            secretAbsentFromSettingsFile: !settingsText.contains(secret),
            snapshotReportsStoredSecret: snapshot.providers.first?.hasSecret == true,
            deleteRemovedSetting: try store.snapshot().providers.isEmpty,
            deleteRemovedCredential: credentialMissing
        )
    }
}
