import Foundation

enum OfficialStyleSamples {
    static func export(to directory: URL) throws {
        let envelope = try Data(contentsOf: catalogEnvelopeURL())
        let store = try TemplateCatalogStore(
            root: FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString),
            bundledEnvelope: envelope
        )
        let catalog = try store.verifiedCatalog(from: envelope)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        for entry in catalog.entries {
            let project = project(for: entry)
            let destination = directory.appendingPathComponent(entry.documentType, isDirectory: true)
            let receipt = try DocumentExportEngine().export(
                project: project,
                request: ExportRequest(
                    operationID: "official-style-\(entry.templateID)",
                    destination: destination,
                    formats: [.docx, .hwpx],
                    flatteningConsent: [.docx, .hwpx]
                )
            )
            guard receipt.publishedFormats.contains(.docx),
                  receipt.publishedFormats.contains(.hwpx)
            else {
                let failures = receipt.failures.map {
                    "\($0.format.rawValue):\($0.stage.rawValue):\($0.errorCode):\($0.userDiagnostic)"
                }.joined(separator: "; ")
                throw ExportError.invalidPackage(
                    "official sample export blocked for \(entry.documentType) published=\(receipt.publishedFormats.map(\.rawValue)) blocked=\(receipt.blockedFormats.map(\.rawValue)) failed=\(receipt.failedFormats.map(\.rawValue)) \(failures)"
                )
            }
        }
    }

    private static func catalogEnvelopeURL() -> URL {
        if let bundled = Bundle.main.resourceURL?
            .appendingPathComponent("Templates/catalog-envelope.json"),
           FileManager.default.fileExists(atPath: bundled.path)
        {
            return bundled
        }
        return URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
            .appendingPathComponent("Resources/Templates/catalog-envelope.json")
    }

    private static func project(for entry: TemplateCatalogEntry) -> DocumentProject {
        var elements = [
            DocumentElement(
                elementID: "element-title",
                kind: "heading",
                order: 0,
                text: entry.documentType,
                styleID: "style-title",
                evidenceIDs: []
            )
        ]
        for (index, section) in entry.requiredSections.enumerated() {
            elements.append(
                DocumentElement(
                    elementID: "element-section-\(index + 1)-heading",
                    kind: "heading",
                    order: elements.count,
                    text: "□ \(section)",
                    styleID: "style-section-heading",
                    evidenceIDs: []
                )
            )
            elements.append(
                DocumentElement(
                    elementID: "element-section-\(index + 1)-body",
                    kind: "paragraph",
                    order: elements.count,
                    text: "○ \(section)",
                    styleID: "style-body",
                    evidenceIDs: []
                )
            )
        }
        for extra in [
            ("element-detail", "- 세부내용", "style-body-detail"),
            ("element-reference-note", "※ 참고내용", "style-reference-note"),
            ("element-annotation", "* 주석내용", "style-annotation"),
        ] {
            elements.append(
                DocumentElement(
                    elementID: extra.0,
                    kind: "paragraph",
                    order: elements.count,
                    text: extra.1,
                    styleID: extra.2,
                    evidenceIDs: []
                )
            )
        }
        let revision = DocumentRevision(
            revisionID: "revision-official-\(entry.templateID)",
            createdAt: "2026-08-15T00:00:00Z",
            summary: "official-style-sample",
            elementIDs: elements.map(\.elementID),
            snapshotElements: elements
        )
        return DocumentProject(
            schemaVersion: 1,
            documentID: "document-official-\(entry.templateID)",
            locale: "ko-KR",
            title: entry.documentType,
            currentRevisionID: revision.revisionID,
            elements: elements,
            assets: [],
            styles: OfficialStyleBinding.presetIDs.map {
                DocumentStyle(styleID: $0, name: $0, properties: [:])
            },
            templateBinding: ProjectTemplateBinding(
                templateID: entry.templateID,
                version: entry.version,
                publishingAuthority: entry.publishingAuthority,
                requiredSections: entry.requiredSections,
                checklistResults: [:]
            ),
            evidenceLinks: [],
            revisions: [revision],
            history: [],
            aiProposalHistory: []
        )
    }
}
