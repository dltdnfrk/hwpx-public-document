import Foundation

struct AIGovernanceEngine {
    static let approvedProviderKinds = AIProviderKind.allCases

    func copy(
        _ project: DocumentProject,
        currentRevisionID: String? = nil,
        elements: [DocumentElement]? = nil,
        revisions: [DocumentRevision]? = nil,
        aiProposalHistory: [AIProposalHistoryRecord]? = nil,
        providerConfigurations: [AIProviderConfiguration]? = nil,
        consentGrants: [AIConsentGrant]? = nil,
        redoRevisionIDs: [String]? = nil
    ) -> DocumentProject {
        DocumentProject(
            schemaVersion: project.schemaVersion, documentID: project.documentID, locale: project.locale,
            title: project.title, currentRevisionID: currentRevisionID ?? project.currentRevisionID,
            elements: elements ?? project.elements, assets: project.assets, styles: project.styles,
            templateBinding: project.templateBinding, evidenceLinks: project.evidenceLinks,
            revisions: revisions ?? project.revisions, history: project.history,
            aiProposalHistory: aiProposalHistory ?? project.aiProposalHistory,
            providerConfigurations: providerConfigurations ?? project.providerConfigurations,
            consentGrants: consentGrants ?? project.consentGrants,
            redoRevisionIDs: redoRevisionIDs ?? project.redoRevisionIDs
        )
    }
}
