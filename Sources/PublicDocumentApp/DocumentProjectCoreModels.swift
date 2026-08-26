import Foundation

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
