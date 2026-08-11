import Foundation

enum ExportAuthoringUniverseFixture {
    static func project() -> DocumentProject {
        makeProject(
            documentID: "document-ac05-authoring-universe",
            revisionID: "revision-ac05-authoring-universe",
            elements: [
                element("element-metadata", "metadata", 0, "생활안전과 · 2026. 8. 9."),
                element("element-heading", "heading", 1, "작성 기능 호환성 표본"),
                element(
                    "element-rich-paragraph",
                    "paragraph",
                    2,
                    "굵게 기울임 밑줄 글꼴 문구 묶음",
                    html: """
                    <strong data-inline-id="inline-paragraph-strong"><em data-inline-id="inline-paragraph-emphasis"><u data-inline-id="inline-paragraph-underline">굵게 기울임 밑줄</u></em></strong>
                    <span data-inline-id="inline-paragraph-font" style="font-family: &quot;Apple SD Gothic Neo&quot;; font-size: 12pt">글꼴</span>
                    <span class="keep-phrase" data-inline-id="inline-paragraph-keep">문구 묶음</span>
                    """,
                    inlineIDs: [
                        "inline-paragraph-strong", "inline-paragraph-emphasis",
                        "inline-paragraph-underline", "inline-paragraph-font", "inline-paragraph-keep",
                    ]
                ),
                element("element-plain-paragraph", "paragraph", 3, "일반 본문"),
                element(
                    "element-unordered-list",
                    "list-item",
                    4,
                    "첫 번째 항목 두 번째 항목",
                    html: "<ul><li><strong data-inline-id=\"inline-list-strong\">첫 번째 항목</strong></li><li>두 번째 항목</li></ul>",
                    inlineIDs: ["inline-list-strong"]
                ),
                element(
                    "element-table",
                    "table",
                    5,
                    "항목 내용 기간 2026. 9. ~ 12.",
                    html: "<table><tbody><tr><th><strong data-inline-id=\"inline-table-strong\">항목</strong></th><th>내용</th></tr><tr><td>기간</td><td>2026. 9. ~ 12.</td></tr></tbody></table>",
                    inlineIDs: ["inline-table-strong"]
                ),
                element(
                    "element-approval",
                    "approval-grid",
                    6,
                    "담당 팀장 과장 김○○",
                    html: "<table><tbody><tr><th>담당</th><th>팀장</th><th>과장</th></tr><tr><td>김○○</td><td></td><td></td></tr></tbody></table>"
                ),
                element(
                    "element-review",
                    "review-marker",
                    7,
                    "[확인 필요] 근거 확인",
                    html: "<strong data-inline-id=\"inline-review-strong\">[확인 필요] 근거 확인</strong>",
                    inlineIDs: ["inline-review-strong"]
                ),
                element("element-formula", "formula", 8, "안전지수 = 조치완료 / 점검대상"),
            ]
        )
    }

    static func visualOnlyProject() -> DocumentProject {
        let rich = element(
            "element-visual-only",
            "paragraph",
            0,
            "굵게 기울임 밑줄 글꼴 문구 묶음",
            html: """
            <strong data-inline-id="inline-visual-strong"><em data-inline-id="inline-visual-emphasis"><u data-inline-id="inline-visual-underline">굵게 기울임 밑줄</u></em></strong>
            <span data-inline-id="inline-visual-font" style="font-family: serif; font-size: 14pt">글꼴</span>
            <span class="keep-phrase" data-inline-id="inline-visual-keep">문구 묶음</span>
            """,
            inlineIDs: [
                "inline-visual-strong", "inline-visual-emphasis", "inline-visual-underline",
                "inline-visual-font", "inline-visual-keep",
            ]
        )
        return makeProject(
            documentID: "document-ac05-visual-unconsented",
            revisionID: "revision-ac05-visual-unconsented",
            elements: [rich]
        )
    }

    private static func makeProject(
        documentID: String,
        revisionID: String,
        elements: [DocumentElement]
    ) -> DocumentProject {
        let revision = DocumentRevision(
            revisionID: revisionID,
            createdAt: "2026-08-09T00:00:00Z",
            summary: "AC-05 frozen capability fixture",
            elementIDs: elements.map(\.elementID)
        )
        return DocumentProject(
            schemaVersion: 1,
            documentID: documentID,
            locale: "ko-KR",
            title: "작성 기능 호환성 표본",
            currentRevisionID: revisionID,
            elements: elements,
            assets: [],
            styles: [DocumentStyle(styleID: "style-body", name: "본문", properties: ["font": "본고딕"])],
            templateBinding: ProjectTemplateBinding(
                templateID: "public-plan",
                version: "3.2",
                publishingAuthority: "기관 표준",
                requiredSections: ["개요"],
                checklistResults: ["목적과 대상": true]
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

    private static func element(
        _ elementID: String,
        _ kind: String,
        _ order: Int,
        _ text: String,
        html: String? = nil,
        inlineIDs: [String] = []
    ) -> DocumentElement {
        DocumentElement(
            elementID: elementID,
            kind: kind,
            order: order,
            text: text,
            contentHTML: html ?? "<span>\(text)</span>",
            inlineIDs: inlineIDs,
            styleID: "style-body",
            evidenceIDs: []
        )
    }
}
