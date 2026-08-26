import Foundation

extension AIGovernanceSelfTest {
    static func fixture() -> DocumentProject {
        let elements = [
            DocumentElement(elementID: "element-title", kind: "heading", order: 0, text: "공공문서", styleID: "title", evidenceIDs: []),
            DocumentElement(elementID: "element-body", kind: "paragraph", order: 1, text: "기존 본문", styleID: "body", evidenceIDs: ["evidence-1"]),
            DocumentElement(elementID: "element-summary", kind: "paragraph", order: 2, text: "기존 요약", styleID: "body", evidenceIDs: []),
            DocumentElement(
                elementID: "element-table", kind: "table", order: 3, text: "항목 값 대상 보존",
                contentHTML: "<table><tbody><tr><th data-cell=\"header\">항목</th><th>값</th></tr><tr><td data-cell=\"target\">대상</td><td data-cell=\"keep\"><strong>보존</strong></td></tr></tbody></table>",
                inlineIDs: ["inline-table-keep"], styleID: "body", evidenceIDs: []
            ),
        ]
        let revision = DocumentRevision(
            revisionID: "revision-base", createdAt: "2026-08-09T00:00:00Z", summary: "created",
            elementIDs: elements.map(\.elementID), snapshotElements: elements
        )
        return DocumentProject(
            schemaVersion: 1, documentID: "document-ac04", locale: "ko-KR", title: "공공문서",
            currentRevisionID: revision.revisionID, elements: elements, assets: [],
            styles: [DocumentStyle(styleID: "body", name: "본문", properties: [:])],
            templateBinding: ProjectTemplateBinding(
                templateID: "public-plan", version: "3.2", publishingAuthority: "기관 표준",
                requiredSections: ["본문"], checklistResults: ["본문": true]
            ),
            evidenceLinks: [], revisions: [revision],
            history: [ProjectHistoryEvent(eventID: "history-base", kind: "created", revisionID: revision.revisionID, createdAt: revision.createdAt)],
            aiProposalHistory: [],
            providerConfigurations: [AIProviderConfiguration(
                provider: "openai", endpointIdentity: "https://api.openai.com/v1",
                keychainAccountReference: "keychain://public-document-studio/openai"
            )]
        )
    }
}
