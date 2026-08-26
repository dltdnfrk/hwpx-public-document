import Foundation

extension BatchExportSelfTest {
    static func request(
        operationID: String,
        retryOfOperationID: String? = nil,
        root: URL,
        documents: [BatchDocumentInput],
        formats: [DocumentFormat]
    ) -> BatchExportRequest {
        BatchExportRequest(
            operationID: operationID,
            retryOfOperationID: retryOfOperationID,
            destination: root,
            documents: documents,
            formats: formats,
            flatteningConsent: Set(formats)
        )
    }

    static func fixtures() -> [BatchDocumentInput] {
        [
            BatchDocumentInput(
                project: fixtureProject(
                    documentID: "document-ac06-a",
                    revisionID: "revision-ac06-a",
                    title: "생활안전 계획",
                    text: "생활안전 점검 계획을 수립한다."
                ),
                fileStem: "생활안전-계획"
            ),
            BatchDocumentInput(
                project: fixtureProject(
                    documentID: "document-ac06-b",
                    revisionID: "revision-ac06-b",
                    title: "시설점검 보고",
                    text: "시설점검 결과를 보고한다."
                ),
                fileStem: "시설점검-보고"
            ),
        ]
    }

    static func fixtureProject(
        documentID: String,
        revisionID: String,
        title: String,
        text: String
    ) -> DocumentProject {
        let element = DocumentElement(
            elementID: "element-\(documentID)",
            kind: "paragraph",
            order: 0,
            text: text,
            contentHTML: "<span>\(text)</span>",
            styleID: "style-body",
            evidenceIDs: []
        )
        let revision = DocumentRevision(
            revisionID: revisionID,
            createdAt: "2026-08-09T00:00:00Z",
            summary: "AC-06 immutable batch fixture",
            elementIDs: [element.elementID],
            snapshotElements: [element]
        )
        return DocumentProject(
            schemaVersion: 1,
            documentID: documentID,
            locale: "ko-KR",
            title: title,
            currentRevisionID: revisionID,
            elements: [element],
            assets: [],
            styles: [DocumentStyle(styleID: "style-body", name: "본문", properties: [:])],
            templateBinding: ProjectTemplateBinding(
                templateID: "public-plan",
                version: "3.2",
                publishingAuthority: "기관 표준",
                requiredSections: [],
                checklistResults: [:]
            ),
            evidenceLinks: [],
            revisions: [revision],
            history: [ProjectHistoryEvent(
                eventID: "history-\(documentID)",
                kind: "created",
                revisionID: revisionID,
                createdAt: revision.createdAt
            )],
            aiProposalHistory: []
        )
    }
}
