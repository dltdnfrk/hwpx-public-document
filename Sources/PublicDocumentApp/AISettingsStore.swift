import Foundation

final class AISettingsStore {
    private let root: URL
    private let credentials: AIKeychainCredentialStore
    private let fileManager: FileManager

    init(
        root: URL = AISettingsStore.defaultRoot(),
        credentials: AIKeychainCredentialStore = AIKeychainCredentialStore(),
        fileManager: FileManager = .default
    ) {
        self.root = root
        self.credentials = credentials
        self.fileManager = fileManager
    }

    static func defaultRoot() -> URL {
        if let override = ProcessInfo.processInfo.environment["PUBLIC_DOCUMENT_STUDIO_AI_SETTINGS_ROOT"] {
            return URL(fileURLWithPath: override, isDirectory: true)
        }
        return FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("PublicDocumentStudio", isDirectory: true)
    }

    func load() throws -> AISettingsFile {
        let url = root.appendingPathComponent("ai-settings.json")
        guard fileManager.fileExists(atPath: url.path) else { return .empty }
        let settings = try JSONDecoder().decode(
            AISettingsFile.self,
            from: Data(contentsOf: url)
        )
        guard settings.schemaVersion == AISettingsFile.empty.schemaVersion else {
            throw AISettingsError.invalidSettings
        }
        return settings
    }

    func setting(for provider: AIProviderKind) throws -> AIProviderSetting {
        guard let setting = try load().providers[provider.rawValue] else {
            throw AISettingsError.notConfigured
        }
        return setting
    }

    func activeSetting() throws -> AIProviderSetting {
        let settings = try load()
        guard let active = settings.activeProvider,
              let setting = settings.providers[active]
        else { throw AISettingsError.notConfigured }
        return setting
    }

    func snapshot() throws -> AISettingsSnapshot {
        let settings = try load()
        let providers = try settings.providers.values.sorted { $0.provider < $1.provider }.map { setting in
            AIProviderSettingStatus(
                provider: setting.provider,
                endpointIdentity: setting.endpointIdentity,
                model: setting.model,
                hasSecret: try credentials.contains(accountReference: setting.keychainAccountReference),
                hostDisclosure: URL(string: setting.endpointIdentity)?.host ?? ""
            )
        }
        return AISettingsSnapshot(
            activeProvider: settings.activeProvider,
            providers: providers,
            catalog: AIProviderCatalog.policies
        )
    }

    @discardableResult
    func save(
        provider: AIProviderKind,
        endpointIdentity: String,
        model: String,
        secret: String?
    ) throws -> AIProviderSetting {
        let endpoint = endpointIdentity.trimmingCharacters(in: .whitespacesAndNewlines)
            .trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        let trimmedModel = model.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let url = URL(string: endpoint),
              url.user == nil,
              url.password == nil,
              url.fragment == nil,
              AIProviderTransport.endpointIsAllowed(url, provider: provider)
        else { throw AISettingsError.invalidEndpoint }
        let allowedModelCharacters = CharacterSet.alphanumerics
            .union(CharacterSet(charactersIn: "-._:/"))
        guard !trimmedModel.isEmpty,
              trimmedModel.count <= 160,
              !trimmedModel.contains(".."),
              !trimmedModel.hasPrefix("/"),
              trimmedModel.unicodeScalars.allSatisfy({ allowedModelCharacters.contains($0) })
        else {
            throw AISettingsError.invalidModel
        }
        var settings = try load()
        let existing = settings.providers[provider.rawValue]
        if let existing, existing.endpointIdentity != endpoint, secret == nil {
            throw AISettingsError.invalidSecret
        }
        let account = existing?.keychainAccountReference ?? "provider/\(provider.rawValue)"
        if let secret {
            guard !secret.isEmpty, secret.utf8.count <= 8192 else {
                throw AISettingsError.invalidSecret
            }
            try credentials.set(secret: secret, accountReference: account)
        } else if (try? credentials.get(accountReference: account)) == nil {
            throw AISettingsError.invalidSecret
        }
        let setting = AIProviderSetting(
            provider: provider.rawValue,
            endpointIdentity: endpoint,
            model: trimmedModel,
            keychainAccountReference: account
        )
        settings.providers[provider.rawValue] = setting
        settings.activeProvider = provider.rawValue
        try write(settings)
        return setting
    }

    func delete(provider: AIProviderKind) throws {
        var settings = try load()
        if let setting = settings.providers.removeValue(forKey: provider.rawValue) {
            try credentials.delete(accountReference: setting.keychainAccountReference)
        }
        if settings.activeProvider == provider.rawValue {
            settings.activeProvider = settings.providers.keys.sorted().first
        }
        try write(settings)
    }

    @discardableResult
    func migrateLegacyConfigurations(_ configurations: [AIProviderConfiguration]) throws -> Bool {
        var knownProviders = Set(try load().providers.keys)
        var migrated = false
        for configuration in configurations {
            guard let provider = AIProviderKind(rawValue: configuration.provider),
                  !knownProviders.contains(provider.rawValue),
                  let secret = try? credentials.get(
                      accountReference: configuration.keychainAccountReference
                  )
            else {
                continue
            }
            let configuredModel = configuration.model?.trimmingCharacters(in: .whitespacesAndNewlines)
            let model = configuredModel.flatMap { $0.isEmpty ? nil : $0 }
                ?? AIProviderCatalog.policy(for: provider).defaultModel
            _ = try save(
                provider: provider,
                endpointIdentity: configuration.endpointIdentity,
                model: model,
                secret: secret
            )
            knownProviders.insert(provider.rawValue)
            migrated = true
        }
        return migrated
    }

    func credential(for setting: AIProviderSetting) throws -> String {
        try credentials.get(accountReference: setting.keychainAccountReference)
    }

    private func write(_ settings: AISettingsFile) throws {
        try fileManager.createDirectory(at: root, withIntermediateDirectories: true)
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        let url = root.appendingPathComponent("ai-settings.json")
        try encoder.encode(settings).write(to: url, options: .atomic)
        try fileManager.setAttributes([.posixPermissions: 0o600], ofItemAtPath: url.path)
    }
}
