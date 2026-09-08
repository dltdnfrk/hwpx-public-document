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

    func replacingText(_ text: String) -> DocumentElement {
        DocumentElement(
            elementID: elementID, kind: kind, order: order, text: text,
            contentHTML: contentHTML, inlineIDs: inlineIDs, styleID: styleID, evidenceIDs: evidenceIDs
        )
    }
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

    func replacingElements(_ elements: [DocumentElement]) -> DocumentProject {
        DocumentProject(
            schemaVersion: schemaVersion, documentID: documentID, locale: locale, title: title,
            currentRevisionID: currentRevisionID, elements: elements, assets: assets, styles: styles,
            templateBinding: templateBinding, evidenceLinks: evidenceLinks, revisions: revisions,
            history: history, aiProposalHistory: aiProposalHistory,
            providerConfigurations: providerConfigurations, consentGrants: consentGrants,
            redoRevisionIDs: redoRevisionIDs
        )
    }
}
