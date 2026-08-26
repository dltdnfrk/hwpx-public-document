import Foundation

final class DocumentProjectStore {
    static let currentSchemaVersion = 1

    private let root: URL
    private let fileManager: FileManager
    private let encoder: JSONEncoder
    private let decoder: JSONDecoder

    init(root: URL, fileManager: FileManager = .default) {
        self.root = root
        self.fileManager = fileManager
        encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        decoder = JSONDecoder()
    }

    var projectFile: URL { root.appendingPathComponent("project.json") }
    var recoveryFile: URL { root.appendingPathComponent("recovery.json") }

    func save(_ project: DocumentProject) throws {
        try prepareRoot()
        try encoder.encode(project).write(to: projectFile, options: [.atomic])
        if fileManager.fileExists(atPath: recoveryFile.path) {
            try fileManager.removeItem(at: recoveryFile)
        }
    }

    func autosave(_ project: DocumentProject) throws {
        try prepareRoot()
        try encoder.encode(project).write(to: recoveryFile, options: [.atomic])
    }

    func loadCanonical() throws -> DocumentProject {
        try load(from: projectFile)
    }

    func loadRecoveringAutosave() throws -> DocumentProject {
        let source = fileManager.fileExists(atPath: recoveryFile.path) ? recoveryFile : projectFile
        return try load(from: source)
    }

    func inspect(_ project: DocumentProject) -> ProjectInspection {
        ProjectInspection(
            schemaVersion: project.schemaVersion,
            documentID: project.documentID,
            currentRevisionID: project.currentRevisionID,
            elementCount: project.elements.count,
            assetCount: project.assets.count,
            styleCount: project.styles.count,
            evidenceLinkCount: project.evidenceLinks.count,
            revisionCount: project.revisions.count,
            historyEventCount: project.history.count,
            templateID: project.templateBinding.templateID,
            templateVersion: project.templateBinding.version
        )
    }

    func hasProject() -> Bool {
        fileManager.fileExists(atPath: projectFile.path)
    }

    func hasRecovery() -> Bool {
        fileManager.fileExists(atPath: recoveryFile.path)
    }

    private func prepareRoot() throws {
        try fileManager.createDirectory(at: root, withIntermediateDirectories: true)
    }

    private func load(from url: URL) throws -> DocumentProject {
        let data = try Data(contentsOf: url)
        guard
            let container = try JSONSerialization.jsonObject(with: data) as? [String: Any],
            let schemaVersion = container["schemaVersion"] as? Int
        else {
            throw ProjectStoreError.invalidProject
        }
        switch schemaVersion {
        case Self.currentSchemaVersion:
            return try decoder.decode(DocumentProject.self, from: data)
        case 0:
            let migrated = migrate(try decoder.decode(LegacyDocumentProject.self, from: data))
            try save(migrated)
            return migrated
        default:
            throw ProjectStoreError.unsupportedSchema(schemaVersion)
        }
    }

    private func migrate(_ legacy: LegacyDocumentProject) -> DocumentProject {
        let event = ProjectHistoryEvent(
            eventID: "migration-0-to-1",
            kind: "schema-migrated",
            revisionID: legacy.currentRevisionID,
            createdAt: "migration"
        )
        return DocumentProject(
            schemaVersion: Self.currentSchemaVersion,
            documentID: legacy.documentID,
            locale: legacy.locale,
            title: legacy.title,
            currentRevisionID: legacy.currentRevisionID,
            elements: legacy.elements,
            assets: legacy.assets,
            styles: legacy.styles,
            templateBinding: legacy.templateBinding,
            evidenceLinks: legacy.evidenceLinks,
            revisions: legacy.revisions,
            history: legacy.history + [event],
            aiProposalHistory: []
        )
    }
}
