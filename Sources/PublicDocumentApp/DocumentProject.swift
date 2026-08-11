import Foundation

struct DocumentElement: Codable, Equatable {
    let elementID: String
    let kind: String
    let order: Int
    let text: String
    let contentHTML: String
    let inlineIDs: [String]
    let styleID: String
    let evidenceIDs: [String]

    init(
        elementID: String,
        kind: String,
        order: Int,
        text: String,
        contentHTML: String = "",
        inlineIDs: [String] = [],
        styleID: String,
        evidenceIDs: [String]
    ) {
        self.elementID = elementID
        self.kind = kind
        self.order = order
        self.text = text
        self.contentHTML = contentHTML
        self.inlineIDs = inlineIDs
        self.styleID = styleID
        self.evidenceIDs = evidenceIDs
    }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        elementID = try values.decode(String.self, forKey: .elementID)
        kind = try values.decode(String.self, forKey: .kind)
        order = try values.decode(Int.self, forKey: .order)
        text = try values.decode(String.self, forKey: .text)
        contentHTML = try values.decodeIfPresent(String.self, forKey: .contentHTML) ?? ""
        inlineIDs = try values.decodeIfPresent([String].self, forKey: .inlineIDs) ?? []
        styleID = try values.decode(String.self, forKey: .styleID)
        evidenceIDs = try values.decode([String].self, forKey: .evidenceIDs)
    }
}

struct DocumentAsset: Codable, Equatable {
    let assetID: String
    let contentHash: String
    let mediaType: String
    let relativePath: String
}

struct DocumentStyle: Codable, Equatable {
    let styleID: String
    let name: String
    let properties: [String: String]
}

struct ProjectTemplateBinding: Codable, Equatable {
    let templateID: String
    let version: String
    let publishingAuthority: String
    let requiredSections: [String]
    let checklistResults: [String: Bool]
}

struct SourceEvidenceLink: Codable, Equatable {
    let evidenceID: String
    let sourceTitle: String
    let locator: String
    let contentHash: String
    let claimElementIDs: [String]
}

struct DocumentRevision: Codable, Equatable {
    let revisionID: String
    let parentRevisionID: String?
    let createdAt: String
    let summary: String
    let elementIDs: [String]
    let snapshotElements: [DocumentElement]

    init(
        revisionID: String,
        parentRevisionID: String? = nil,
        createdAt: String,
        summary: String,
        elementIDs: [String],
        snapshotElements: [DocumentElement] = []
    ) {
        self.revisionID = revisionID
        self.parentRevisionID = parentRevisionID
        self.createdAt = createdAt
        self.summary = summary
        self.elementIDs = elementIDs
        self.snapshotElements = snapshotElements
    }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        revisionID = try values.decode(String.self, forKey: .revisionID)
        parentRevisionID = try values.decodeIfPresent(String.self, forKey: .parentRevisionID)
        createdAt = try values.decode(String.self, forKey: .createdAt)
        summary = try values.decode(String.self, forKey: .summary)
        elementIDs = try values.decode([String].self, forKey: .elementIDs)
        snapshotElements = try values.decodeIfPresent([DocumentElement].self, forKey: .snapshotElements) ?? []
    }
}

struct ProjectHistoryEvent: Codable, Equatable {
    let eventID: String
    let kind: String
    let revisionID: String
    let createdAt: String
}

struct AIProposalHistoryRecord: Codable, Equatable {
    let proposalID: String
    let baseRevisionID: String
    let state: String
    let targetElementIDs: [String]
    let operation: String
    let provider: String
    let endpointIdentity: String
    let payloadScope: String
    let commands: [AIProposalCommand]
    let diffs: [AIProposalDiff]
    let approvedCommandIDs: [String]
    let createdRevisionID: String?

    init(
        proposalID: String,
        baseRevisionID: String,
        state: String,
        targetElementIDs: [String],
        operation: String = "",
        provider: String = "",
        endpointIdentity: String = "",
        payloadScope: String = "",
        commands: [AIProposalCommand] = [],
        diffs: [AIProposalDiff] = [],
        approvedCommandIDs: [String] = [],
        createdRevisionID: String? = nil
    ) {
        self.proposalID = proposalID
        self.baseRevisionID = baseRevisionID
        self.state = state
        self.targetElementIDs = targetElementIDs
        self.operation = operation
        self.provider = provider
        self.endpointIdentity = endpointIdentity
        self.payloadScope = payloadScope
        self.commands = commands
        self.diffs = diffs
        self.approvedCommandIDs = approvedCommandIDs
        self.createdRevisionID = createdRevisionID
    }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        proposalID = try values.decode(String.self, forKey: .proposalID)
        baseRevisionID = try values.decode(String.self, forKey: .baseRevisionID)
        state = try values.decode(String.self, forKey: .state)
        targetElementIDs = try values.decode([String].self, forKey: .targetElementIDs)
        operation = try values.decodeIfPresent(String.self, forKey: .operation) ?? ""
        provider = try values.decodeIfPresent(String.self, forKey: .provider) ?? ""
        endpointIdentity = try values.decodeIfPresent(String.self, forKey: .endpointIdentity) ?? ""
        payloadScope = try values.decodeIfPresent(String.self, forKey: .payloadScope) ?? ""
        commands = try values.decodeIfPresent([AIProposalCommand].self, forKey: .commands) ?? []
        diffs = try values.decodeIfPresent([AIProposalDiff].self, forKey: .diffs) ?? []
        approvedCommandIDs = try values.decodeIfPresent([String].self, forKey: .approvedCommandIDs) ?? []
        createdRevisionID = try values.decodeIfPresent(String.self, forKey: .createdRevisionID)
    }
}

struct AIProposalCommand: Codable, Equatable {
    let commandID: String
    let name: String
    let targetElementID: String
    let value: String
    let targetPath: String?

    init(commandID: String, name: String, targetElementID: String, value: String, targetPath: String? = nil) {
        self.commandID = commandID; self.name = name; self.targetElementID = targetElementID; self.value = value; self.targetPath = targetPath
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        commandID = try c.decode(String.self, forKey: .commandID); name = try c.decode(String.self, forKey: .name)
        targetElementID = try c.decode(String.self, forKey: .targetElementID); value = try c.decode(String.self, forKey: .value)
        targetPath = try c.decodeIfPresent(String.self, forKey: .targetPath)
    }
}

struct AIProviderConfiguration: Codable, Equatable {
    let provider: String
    let endpointIdentity: String
    let keychainAccountReference: String
}

struct AIConsentGrant: Codable, Equatable {
    let grantID: String
    let documentID: String
    let provider: String
    let endpointIdentity: String
    let operation: String
    let payloadScope: String
    let revoked: Bool
}

struct DocumentProject: Codable, Equatable {
    let schemaVersion: Int
    let documentID: String
    let locale: String
    let title: String
    let currentRevisionID: String
    let elements: [DocumentElement]
    let assets: [DocumentAsset]
    let styles: [DocumentStyle]
    let templateBinding: ProjectTemplateBinding
    let evidenceLinks: [SourceEvidenceLink]
    let revisions: [DocumentRevision]
    let history: [ProjectHistoryEvent]
    let aiProposalHistory: [AIProposalHistoryRecord]
    let providerConfigurations: [AIProviderConfiguration]
    let consentGrants: [AIConsentGrant]
    let redoRevisionIDs: [String]

    init(
        schemaVersion: Int,
        documentID: String,
        locale: String,
        title: String,
        currentRevisionID: String,
        elements: [DocumentElement],
        assets: [DocumentAsset],
        styles: [DocumentStyle],
        templateBinding: ProjectTemplateBinding,
        evidenceLinks: [SourceEvidenceLink],
        revisions: [DocumentRevision],
        history: [ProjectHistoryEvent],
        aiProposalHistory: [AIProposalHistoryRecord],
        providerConfigurations: [AIProviderConfiguration] = [],
        consentGrants: [AIConsentGrant] = [],
        redoRevisionIDs: [String] = []
    ) {
        self.schemaVersion = schemaVersion
        self.documentID = documentID
        self.locale = locale
        self.title = title
        self.currentRevisionID = currentRevisionID
        self.elements = elements
        self.assets = assets
        self.styles = styles
        self.templateBinding = templateBinding
        self.evidenceLinks = evidenceLinks
        self.revisions = revisions
        self.history = history
        self.aiProposalHistory = aiProposalHistory
        self.providerConfigurations = providerConfigurations
        self.consentGrants = consentGrants
        self.redoRevisionIDs = redoRevisionIDs
    }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = try values.decode(Int.self, forKey: .schemaVersion)
        documentID = try values.decode(String.self, forKey: .documentID)
        locale = try values.decode(String.self, forKey: .locale)
        title = try values.decode(String.self, forKey: .title)
        currentRevisionID = try values.decode(String.self, forKey: .currentRevisionID)
        elements = try values.decode([DocumentElement].self, forKey: .elements)
        assets = try values.decode([DocumentAsset].self, forKey: .assets)
        styles = try values.decode([DocumentStyle].self, forKey: .styles)
        templateBinding = try values.decode(ProjectTemplateBinding.self, forKey: .templateBinding)
        evidenceLinks = try values.decode([SourceEvidenceLink].self, forKey: .evidenceLinks)
        revisions = try values.decode([DocumentRevision].self, forKey: .revisions)
        history = try values.decode([ProjectHistoryEvent].self, forKey: .history)
        aiProposalHistory = try values.decodeIfPresent([AIProposalHistoryRecord].self, forKey: .aiProposalHistory) ?? []
        providerConfigurations = try values.decodeIfPresent([AIProviderConfiguration].self, forKey: .providerConfigurations) ?? []
        consentGrants = try values.decodeIfPresent([AIConsentGrant].self, forKey: .consentGrants) ?? []
        redoRevisionIDs = try values.decodeIfPresent([String].self, forKey: .redoRevisionIDs) ?? []
    }
}

struct LegacyDocumentProject: Codable {
    let schemaVersion: Int
    let documentID: String
    let locale: String
    let title: String
    let currentRevisionID: String
    let elements: [DocumentElement]
    let assets: [DocumentAsset]
    let styles: [DocumentStyle]
    let templateBinding: ProjectTemplateBinding
    let evidenceLinks: [SourceEvidenceLink]
    let revisions: [DocumentRevision]
    let history: [ProjectHistoryEvent]
}

enum ProjectStoreError: Error, LocalizedError {
    case unsupportedSchema(Int)
    case invalidProject

    var errorDescription: String? {
        switch self {
        case .unsupportedSchema(let version):
            return "지원하지 않는 프로젝트 스키마 버전입니다: \(version)"
        case .invalidProject:
            return "프로젝트 파일을 읽을 수 없습니다."
        }
    }
}

struct ProjectInspection: Codable {
    let schemaVersion: Int
    let documentID: String
    let currentRevisionID: String
    let elementCount: Int
    let assetCount: Int
    let styleCount: Int
    let evidenceLinkCount: Int
    let revisionCount: Int
    let historyEventCount: Int
    let templateID: String
    let templateVersion: String
}

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
