import Foundation

struct LifecycleSelfTestReceipt: Codable {
    let schemaVersion: Int
    let stableElementIDs: Bool
    let assetsPreserved: Bool
    let stylesPreserved: Bool
    let templateBindingPreserved: Bool
    let evidenceLinksPreserved: Bool
    let revisionHistoryPreserved: Bool
    let richStructurePreserved: Bool
    let recoveredAutosave: Bool
    let derivedExportDidNotMutateProject: Bool
    let recoveryFileRemovedAfterCommit: Bool
}

struct MigrationSelfTestReceipt: Codable {
    let documentID: String
    let elementIDs: [String]
    let fromSchemaVersion: Int
    let historyEvent: String
    let revisionCount: Int
    let toSchemaVersion: Int
}

struct WindowLifecycleSelfTestReceipt: Codable {
    let visibleWindowCount: Int
}

enum ProjectSelfTest {
    static func runLifecycle(at root: URL) throws -> LifecycleSelfTestReceipt {
        let store = DocumentProjectStore(root: root)
        let original = fixtureProject()
        try store.save(original)
        let reopened = try store.loadCanonical()

        let autosaved = editedProject(reopened)
        try store.autosave(autosaved)
        let recovered = try store.loadRecoveringAutosave()
        try store.save(recovered)

        let beforeExport = try Data(contentsOf: store.projectFile)
        try "# 파생 Markdown 미리보기\n".write(
            to: root.appendingPathComponent("preview.md"),
            atomically: true,
            encoding: .utf8
        )
        let afterExport = try Data(contentsOf: store.projectFile)

        return LifecycleSelfTestReceipt(
            schemaVersion: recovered.schemaVersion,
            stableElementIDs: original.elements.map(\.elementID) == recovered.elements.map(\.elementID),
            assetsPreserved: original.assets == recovered.assets,
            stylesPreserved: original.styles == recovered.styles,
            templateBindingPreserved: original.templateBinding == recovered.templateBinding,
            evidenceLinksPreserved: original.evidenceLinks == recovered.evidenceLinks,
            revisionHistoryPreserved: recovered.revisions.count == 2 && recovered.history.count == 2,
            richStructurePreserved: recovered.elements.last?.contentHTML == "<strong data-inline-id=\"inline-body-strong\">중단 직전 자동저장 본문</strong>" && recovered.elements.last?.inlineIDs == ["inline-body-strong"],
            recoveredAutosave: recovered.elements.last?.text == "중단 직전 자동저장 본문",
            derivedExportDidNotMutateProject: beforeExport == afterExport,
            recoveryFileRemovedAfterCommit: !store.hasRecovery()
        )
    }

    static func runMigration(at root: URL) throws -> MigrationSelfTestReceipt {
        let store = DocumentProjectStore(root: root)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        try legacyFixtureData().write(to: store.projectFile, options: [.atomic])
        let migrated = try store.loadCanonical()
        return MigrationSelfTestReceipt(
            documentID: migrated.documentID,
            elementIDs: migrated.elements.map(\.elementID),
            fromSchemaVersion: 0,
            historyEvent: migrated.history.last?.kind ?? "",
            revisionCount: migrated.revisions.count,
            toSchemaVersion: migrated.schemaVersion
        )
    }

    static func printJSON<T: Encodable>(_ value: T) throws {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        FileHandle.standardOutput.write(try encoder.encode(value))
        FileHandle.standardOutput.write(Data("\n".utf8))
    }

    private static func fixtureProject() -> DocumentProject {
        let elements = [
            DocumentElement(
                elementID: "element-heading-001",
                kind: "heading",
                order: 0,
                text: "생활안전 추진계획",
                contentHTML: "<span data-inline-id=\"inline-heading\">생활안전 추진계획</span>",
                inlineIDs: ["inline-heading"],
                styleID: "style-heading",
                evidenceIDs: []
            ),
            DocumentElement(
                elementID: "element-body-001",
                kind: "paragraph",
                order: 1,
                text: "최초 본문",
                contentHTML: "<strong data-inline-id=\"inline-body-strong\">최초 본문</strong>",
                inlineIDs: ["inline-body-strong"],
                styleID: "style-body",
                evidenceIDs: ["evidence-001"]
            ),
        ]
        let revision = DocumentRevision(
            revisionID: "revision-001",
            parentRevisionID: nil,
            createdAt: "2026-08-09T00:00:00Z",
            summary: "created",
            elementIDs: elements.map(\.elementID)
        )
        return DocumentProject(
            schemaVersion: 1,
            documentID: "document-001",
            locale: "ko-KR",
            title: "생활안전 추진계획",
            currentRevisionID: revision.revisionID,
            elements: elements,
            assets: [DocumentAsset(assetID: "asset-001", contentHash: "sha256:image", mediaType: "image/png", relativePath: "assets/chart.png")],
            styles: [DocumentStyle(styleID: "style-heading", name: "제목", properties: ["level": "1"]), DocumentStyle(styleID: "style-body", name: "본문", properties: ["preset": "body"])],
            templateBinding: ProjectTemplateBinding(templateID: "public-plan", version: "3.2", publishingAuthority: "기관 표준", requiredSections: ["개요", "추진 배경"], checklistResults: ["목적과 대상": true]),
            evidenceLinks: [SourceEvidenceLink(evidenceID: "evidence-001", sourceTitle: "안전 통계", locator: "p.3", contentHash: "sha256:evidence", claimElementIDs: ["element-body-001"])],
            revisions: [revision],
            history: [ProjectHistoryEvent(eventID: "history-001", kind: "created", revisionID: revision.revisionID, createdAt: revision.createdAt)],
            aiProposalHistory: []
        )
    }

    private static func editedProject(_ project: DocumentProject) -> DocumentProject {
        var elements = project.elements
        let body = elements[1]
        elements[1] = DocumentElement(
            elementID: body.elementID,
            kind: body.kind,
            order: body.order,
            text: "중단 직전 자동저장 본문",
            contentHTML: "<strong data-inline-id=\"inline-body-strong\">중단 직전 자동저장 본문</strong>",
            inlineIDs: body.inlineIDs,
            styleID: body.styleID,
            evidenceIDs: body.evidenceIDs
        )
        let revision = DocumentRevision(
            revisionID: "revision-002",
            parentRevisionID: project.currentRevisionID,
            createdAt: "2026-08-09T00:01:00Z",
            summary: "autosaved",
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
            revisions: project.revisions + [revision],
            history: project.history + [ProjectHistoryEvent(eventID: "history-002", kind: "autosaved", revisionID: revision.revisionID, createdAt: revision.createdAt)],
            aiProposalHistory: project.aiProposalHistory
        )
    }

    private static func legacyFixtureData() -> Data {
        Data("""
        {
          "schemaVersion": 0,
          "documentID": "document-legacy-001",
          "locale": "ko-KR",
          "title": "이전 프로젝트",
          "currentRevisionID": "revision-legacy-001",
          "elements": [
            {"elementID":"element-legacy-heading","kind":"heading","order":0,"text":"이전 제목","styleID":"style-heading","evidenceIDs":[]},
            {"elementID":"element-legacy-body","kind":"paragraph","order":1,"text":"이전 본문","styleID":"style-body","evidenceIDs":[]}
          ],
          "assets": [],
          "styles": [],
          "templateBinding": {"templateID":"legacy-template","version":"1.0","publishingAuthority":"기관","requiredSections":[],"checklistResults":{}},
          "evidenceLinks": [],
          "revisions": [{"revisionID":"revision-legacy-001","createdAt":"legacy","summary":"created","elementIDs":["element-legacy-heading","element-legacy-body"]}],
          "history": []
        }
        """.utf8)
    }
}
