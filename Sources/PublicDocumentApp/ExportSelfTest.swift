import Foundation

enum ExportSelfTestScenario: String {
    case allConsented = "all-consented"
    case adversarialMarkdown = "adversarial-markdown"
    case authoringUniverse = "authoring-universe"
    case basicHwpFamily = "basic-hwp-family"
    case markdownUnconsented = "markdown-unconsented"
    case mixedSemanticBlock = "mixed-semantic-block"
    case visualUnconsented = "visual-unconsented"
}

enum ExportSelfTest {
    static func run(at root: URL, scenario: ExportSelfTestScenario) throws -> ExportReceipt {
        let fullProject = scenario == .mixedSemanticBlock ? fixtureProject(includeFormula: true) : fixtureProject(includeFormula: false)
        let project: DocumentProject
        switch scenario {
        case .adversarialMarkdown:
            project = adversarialMarkdownProject(from: fullProject)
        case .authoringUniverse:
            project = ExportAuthoringUniverseFixture.project()
        case .basicHwpFamily:
            project = basicProject(from: fullProject)
        case .markdownUnconsented:
            project = keepTogetherProject(from: fullProject)
        case .allConsented, .mixedSemanticBlock:
            project = fullProject
        case .visualUnconsented:
            project = ExportAuthoringUniverseFixture.visualOnlyProject()
        }
        let formats: [DocumentFormat]
        let consent: Set<DocumentFormat>
        switch scenario {
        case .allConsented, .authoringUniverse:
            formats = DocumentFormat.allCases
            consent = Set(DocumentFormat.allCases)
        case .adversarialMarkdown:
            formats = [.markdown]
            consent = []
        case .basicHwpFamily:
            formats = [.hwpx, .hwp]
            consent = [.hwpx, .hwp]
        case .markdownUnconsented:
            formats = [.markdown]
            consent = []
        case .mixedSemanticBlock:
            formats = [.docx, .markdown]
            consent = [.docx, .markdown]
        case .visualUnconsented:
            formats = DocumentFormat.allCases
            consent = []
        }
        return try DocumentExportEngine().export(
            project: project,
            request: ExportRequest(
                operationID: "operation-ac05-001",
                destination: root,
                formats: formats,
                flatteningConsent: consent
            )
        )
    }

    private static func keepTogetherProject(from project: DocumentProject) -> DocumentProject {
        let elements = project.elements.filter { $0.elementID == "element-summary-body" }
        let revision = DocumentRevision(
            revisionID: "revision-ac05-keep-together",
            createdAt: "2026-08-09T00:00:00Z",
            summary: "keep-together consent fixture",
            elementIDs: elements.map(\.elementID)
        )
        return DocumentProject(
            schemaVersion: project.schemaVersion,
            documentID: "document-ac05-keep-together",
            locale: project.locale,
            title: project.title,
            currentRevisionID: revision.revisionID,
            elements: elements,
            assets: [],
            styles: project.styles,
            templateBinding: project.templateBinding,
            evidenceLinks: [],
            revisions: [revision],
            history: project.history,
            aiProposalHistory: []
        )
    }

    private static func adversarialMarkdownProject(from project: DocumentProject) -> DocumentProject {
        let element = DocumentElement(
            elementID: "element-adversarial-markdown",
            kind: "paragraph",
            order: 0,
            text: "<script>alert(1)</script> *literal* [link](https://invalid.example)",
            contentHTML: "<span data-inline-id=\"inline-adversarial-markdown\">&lt;script&gt;alert(1)&lt;/script&gt; *literal* [link]</span>",
            inlineIDs: ["inline-adversarial-markdown"],
            styleID: "style-body",
            evidenceIDs: []
        )
        let revision = DocumentRevision(
            revisionID: "revision-ac05-adversarial-markdown",
            createdAt: "2026-08-09T00:00:00Z",
            summary: "adversarial Markdown fixture",
            elementIDs: [element.elementID]
        )
        return DocumentProject(
            schemaVersion: project.schemaVersion,
            documentID: "document-ac05-adversarial-markdown",
            locale: project.locale,
            title: project.title,
            currentRevisionID: revision.revisionID,
            elements: [element],
            assets: [],
            styles: project.styles,
            templateBinding: project.templateBinding,
            evidenceLinks: [],
            revisions: [revision],
            history: project.history,
            aiProposalHistory: []
        )
    }

    private static func basicProject(from project: DocumentProject) -> DocumentProject {
        let elements = project.elements.filter { !["table", "approval-grid"].contains($0.kind) }
        let revision = DocumentRevision(
            revisionID: "revision-ac05-basic-hwp-family",
            parentRevisionID: nil,
            createdAt: "2026-08-09T00:00:00Z",
            summary: "text-only HWP family fixture",
            elementIDs: elements.map(\.elementID)
        )
        return DocumentProject(
            schemaVersion: project.schemaVersion,
            documentID: project.documentID,
            locale: project.locale,
            title: project.title,
            currentRevisionID: revision.revisionID,
            elements: elements,
            assets: project.assets,
            styles: project.styles,
            templateBinding: project.templateBinding,
            evidenceLinks: project.evidenceLinks,
            revisions: [revision],
            history: project.history,
            aiProposalHistory: project.aiProposalHistory
        )
    }

    private static func fixtureProject(includeFormula: Bool) -> DocumentProject {
        var elements = fixtureElements()
        if includeFormula {
            elements.append(DocumentElement(
                elementID: "element-formula-001",
                kind: "formula",
                order: 14,
                text: "안전지수 = 조치완료 / 점검대상",
                contentHTML: "<span data-inline-id=\"inline-formula-001\">안전지수 = 조치완료 / 점검대상</span>",
                inlineIDs: ["inline-formula-001"],
                styleID: "style-formula",
                evidenceIDs: []
            ))
        }
        let revision = DocumentRevision(
            revisionID: "revision-ac05-001",
            parentRevisionID: nil,
            createdAt: "2026-08-09T00:00:00Z",
            summary: "frozen nested export fixture",
            elementIDs: elements.map(\.elementID)
        )
        return DocumentProject(
            schemaVersion: 1,
            documentID: "document-ac05-001",
            locale: "ko-KR",
            title: "2026년 생활안전 추진계획",
            currentRevisionID: revision.revisionID,
            elements: elements,
            assets: [],
            styles: [DocumentStyle(styleID: "style-body", name: "본문", properties: ["font": "본고딕"])],
            templateBinding: ProjectTemplateBinding(
                templateID: "public-plan",
                version: "3.2",
                publishingAuthority: "기관 표준",
                requiredSections: ["개요", "추진 배경"],
                checklistResults: ["목적과 대상": true]
            ),
            evidenceLinks: [SourceEvidenceLink(
                evidenceID: "evidence-safety-statistics",
                sourceTitle: "지역 생활안전 통계",
                locator: "p.3",
                contentHash: "sha256:evidence",
                claimElementIDs: ["element-background-body"]
            )],
            revisions: [revision],
            history: [ProjectHistoryEvent(
                eventID: "history-ac05-001",
                kind: "created",
                revisionID: revision.revisionID,
                createdAt: revision.createdAt
            )],
            aiProposalHistory: []
        )
    }

    private static func fixtureElements() -> [DocumentElement] {
        [
            element("element-kicker", "metadata", 0, "생활안전과 · 2026. 8. 9."),
            element("element-title", "heading", 1, "2026년 생활안전 추진계획"),
            element("element-approval", "approval-grid", 2, "담당 팀장 과장 김○○", html: "<span>담당</span><span>팀장</span><span>과장</span><b>김○○</b><b></b><b></b>"),
            element(
                "element-summary-body",
                "paragraph",
                3,
                "지역 생활안전 취약요인을 점검하여 시민이 체감하는 안전 수준을 높이고자 함.",
                html: "지역 생활안전 취약요인을 점검하여 <span class=\"keep-phrase\" data-inline-id=\"inline-summary-keep\">시민이 체감하는 안전 수준을 높이고자 함.</span>",
                inlineIDs: ["inline-summary-text", "inline-summary-keep"]
            ),
            element("element-summary-table", "table", 4, "추진 기간 2026. 9. ~ 2026. 12. 담당 부서 생활안전과", html: "<tbody><tr><th>추진 기간</th><td>2026. 9. ~ 2026. 12.</td></tr><tr><th>담당 부서</th><td>생활안전과</td></tr></tbody>"),
            element("element-background-heading", "heading", 5, "2. 추진 배경"),
            element("element-background-body", "paragraph", 6, "지역 신고 자료를 바탕으로 우선 점검 대상을 선정한다."),
            element("element-evidence-marker", "review-marker", 7, "[확인 필요] 최근 3년 사고 건수의 출처와 기준일"),
            element("element-plan-heading", "heading", 8, "3. 세부 추진계획"),
            element("element-plan-body", "paragraph", 9, "부서별 점검반을 편성하고 현장 점검을 실시한다."),
            element("element-budget-heading", "heading", 10, "4. 예산 및 일정"),
            element("element-budget-body", "paragraph", 11, "[확인 필요] 세부 일정과 소요 예산"),
            element("element-review-heading", "heading", 12, "5. 검토 및 결재"),
            element("element-review-body", "paragraph", 13, "[확인 필요] 검토자와 최종 결재자"),
        ]
    }

    private static func element(
        _ id: String,
        _ kind: String,
        _ order: Int,
        _ text: String,
        html: String? = nil,
        inlineIDs: [String] = []
    ) -> DocumentElement {
        DocumentElement(
            elementID: id,
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
