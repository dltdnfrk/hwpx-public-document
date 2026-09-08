import Foundation

struct FormatCapabilityResource: Decodable {
    let manifestVersion: String
    let matrix: [FormatCapabilityRow]
}

struct FormatCapabilityRow: Decodable {
    let capability: String
    let hwpx: String
    let hwp: String
    let docx: String
    let markdown: String

    func classification(for format: DocumentFormat) -> String {
        switch format {
        case .hwpx: return hwpx
        case .hwp: return hwp
        case .docx: return docx
        case .markdown: return markdown
        }
    }
}

@main
struct ExportFailureHarness {
    static func main() throws {
        let destination = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
        let mode = CommandLine.arguments.dropFirst(2).first
        let element = DocumentElement(
            elementID: "element-runtime-isolation",
            kind: mode == "all-blocked" ? "list-item" : "paragraph",
            order: 0,
            text: "형식별 실패 격리 본문",
            contentHTML: mode == "all-blocked"
                ? "<ul><li>형식별 실패 격리 본문</li></ul>"
                : "<span>형식별 실패 격리 본문</span>",
            styleID: "style-body",
            evidenceIDs: []
        )
        let elements = mode == "duplicate-id"
            ? [element, element]
            : [element]
        let revision = DocumentRevision(
            revisionID: "revision-runtime-isolation",
            createdAt: "2026-08-10T00:00:00Z",
            summary: "runtime failure isolation fixture",
            elementIDs: elements.map(\.elementID),
            snapshotElements: elements
        )
        let project = DocumentProject(
            schemaVersion: 1,
            documentID: "document-runtime-isolation",
            locale: "ko-KR",
            title: "형식별 실패 격리",
            currentRevisionID: revision.revisionID,
            elements: elements,
            assets: [],
            styles: [DocumentStyle(styleID: "style-body", name: "본문", properties: [:])],
            templateBinding: ProjectTemplateBinding(
                templateID: "runtime-isolation",
                version: "1.0.0",
                publishingAuthority: "test",
                requiredSections: [],
                checklistResults: [:]
            ),
            evidenceLinks: [],
            revisions: [revision],
            history: [],
            aiProposalHistory: []
        )
        let formats = ["all-formats", "all-blocked"].contains(mode)
            ? DocumentFormat.allCases
            : [.hwpx, .docx, .markdown]
        let receipt = try DocumentExportEngine().export(
            project: project,
            request: ExportRequest(
                operationID: "operation-runtime-isolation",
                destination: destination,
                formats: formats,
                flatteningConsent: Set(formats)
            )
        )
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        FileHandle.standardOutput.write(try encoder.encode(receipt))
    }
}
