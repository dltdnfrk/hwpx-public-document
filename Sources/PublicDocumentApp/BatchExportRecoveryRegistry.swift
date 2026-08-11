import Foundation

final class BatchExportRecoveryRegistry {
    private static let destinationsKey = "PublicDocumentStudio.BatchExportDestinations"
    private let defaults: UserDefaults

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
    }

    func remember(_ destination: URL) {
        var paths = defaults.stringArray(forKey: Self.destinationsKey) ?? []
        paths.removeAll { $0 == destination.path }
        paths.insert(destination.path, at: 0)
        defaults.set(Array(paths.prefix(12)), forKey: Self.destinationsKey)
    }

    func destinations() -> [URL] {
        (defaults.stringArray(forKey: Self.destinationsKey) ?? []).map {
            URL(fileURLWithPath: $0, isDirectory: true)
        }
    }
}
