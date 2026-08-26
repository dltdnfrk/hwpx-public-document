import Darwin
import Foundation

struct AISettingsSelfTestReceipt: Codable {
    let modelPersisted: Bool
    let modelUsedByTransport: Bool
    let secretAbsentFromSettingsFile: Bool
    let snapshotReportsStoredSecret: Bool
    let endpointChangeRequiresReplacementSecret: Bool
    let legacyCredentialMigrated: Bool
    let providerCatalogIncluded: Bool
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
        let endpointChangeRejected: Bool
        do {
            _ = try store.save(
                provider: provider,
                endpointIdentity: "http://127.0.0.1:19000/v1",
                model: "audit-model",
                secret: nil
            )
            endpointChangeRejected = false
        } catch AISettingsError.invalidSecret {
            endpointChangeRejected = try store.setting(for: provider).endpointIdentity == setting.endpointIdentity
        }
        let legacyAccount = "provider-credential-legacy"
        let legacySecret = "AI-SETTINGS-LEGACY-SECRET"
        let credentialStore = AIKeychainCredentialStore(service: service)
        try credentialStore.set(secret: legacySecret, accountReference: legacyAccount)
        defer { try? credentialStore.delete(accountReference: legacyAccount) }
        let migrated = try store.migrateLegacyConfigurations([
            AIProviderConfiguration(
                provider: AIProviderKind.anthropic.rawValue,
                endpointIdentity: AIProviderCatalog.policy(for: .anthropic).endpointIdentity,
                keychainAccountReference: legacyAccount
            ),
        ])
        let migratedSetting = try store.setting(for: .anthropic)
        let migratedCredential = try store.credential(for: migratedSetting)
        let legacyCredentialMigrated = migrated
            && migratedSetting.model == AIProviderCatalog.policy(for: .anthropic).defaultModel
            && migratedCredential == legacySecret
        try store.delete(provider: provider)
        try store.delete(provider: .anthropic)
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
            endpointChangeRequiresReplacementSecret: endpointChangeRejected,
            legacyCredentialMigrated: legacyCredentialMigrated,
            providerCatalogIncluded: snapshot.catalog == AIProviderCatalog.policies,
            deleteRemovedSetting: try store.snapshot().providers.isEmpty,
            deleteRemovedCredential: credentialMissing
        )
    }
}
