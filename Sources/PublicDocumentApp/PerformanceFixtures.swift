import CryptoKit
import Foundation

struct PerformanceFixture {
    let fixtureID: String
    let declaredPageCount: Int?
    let project: DocumentProject
}

private struct PerformanceFixtureSeed {
    let documentID: String
    let revisionID: String
    let title: String
    let revisionSummary: String
    let elements: [DocumentElement]
}

enum PerformanceFixtures {
    static func hundredPage(elementCount: Int) -> PerformanceFixture {
        let elements = (1...elementCount).map { block in
            let page = (block - 1) * 100 / elementCount + 1
            return DocumentElement(
                elementID: "performance-page-\(page)-block-\(block)",
                kind: "paragraph",
                order: block - 1,
                text: "쪽 \(page) 공공문서 성능 검증 문단 \(block)",
                styleID: "performance-body",
                evidenceIDs: []
            )
        }
        return PerformanceFixture(
            fixtureID: "100-page",
            declaredPageCount: 100,
            project: project(PerformanceFixtureSeed(
                documentID: "performance-100-page",
                revisionID: "performance-100-page-revision",
                title: "100쪽 공공문서 성능 검증",
                revisionSummary: "100 stable page blocks",
                elements: elements
            ))
        )
    }

    static func fiftyMegabytes(
        minimumAuthoredUTF8Bytes: Int,
        elementChunkBytes: Int
    ) throws -> PerformanceFixture {
        guard minimumAuthoredUTF8Bytes > 0, elementChunkBytes > 0 else {
            throw ExportError.invalidPackage("50 MiB 작성 콘텐츠 fixture 기준")
        }
        let elementCount = (minimumAuthoredUTF8Bytes + elementChunkBytes - 1) / elementChunkBytes
        let baseElementBytes = minimumAuthoredUTF8Bytes / elementCount
        let remainder = minimumAuthoredUTF8Bytes % elementCount
        let authoredLine = String(String(repeating: "공공문서성능검증작성내용", count: 11).prefix(128))
            .decomposedStringWithCanonicalMapping
        let authoredLineUnit = authoredLine + "\n"
        let authoredFiller = "각".decomposedStringWithCanonicalMapping
        var elements: [DocumentElement] = []
        elements.reserveCapacity(elementCount)
        for index in 0..<elementCount {
            let targetBytes = baseElementBytes + (index < remainder ? 1 : 0)
            var text = String(format: "AC09AUTHORED%06d\n", index)
            let lineCount = (targetBytes - text.utf8.count) / authoredLineUnit.utf8.count
            text += String(repeating: authoredLineUnit, count: lineCount)
            let fillerBytes = targetBytes - text.utf8.count
            guard fillerBytes >= 0 else {
                throw ExportError.invalidPackage("50 MiB 작성 콘텐츠 청크 기준")
            }
            text += String(repeating: authoredFiller, count: fillerBytes / authoredFiller.utf8.count)
                + String(repeating: "x", count: fillerBytes % authoredFiller.utf8.count)
            elements.append(DocumentElement(
                elementID: String(format: "performance-authored-content-%06d", index),
                kind: "paragraph",
                order: index,
                text: text,
                styleID: "performance-body",
                evidenceIDs: []
            ))
        }
        let projectValue = project(PerformanceFixtureSeed(
            documentID: "performance-50-mb",
            revisionID: "performance-50-mb-revision",
            title: "50 MB 공공문서 성능 검증",
            revisionSummary: "50 MiB app-authored element corpus",
            elements: elements
        ))
        return PerformanceFixture(fixtureID: "50-mb", declaredPageCount: nil, project: projectValue)
    }

    static func interaction() -> DocumentProject {
        project(PerformanceFixtureSeed(
            documentID: "performance-interaction",
            revisionID: "performance-interaction-revision",
            title: "상호작용 성능 검증",
            revisionSummary: "interaction thresholds",
            elements: [DocumentElement(
                elementID: "performance-interaction-body",
                kind: "paragraph",
                order: 0,
                text: "진행률과 취소 응답을 검증합니다.",
                styleID: "performance-body",
                evidenceIDs: []
            )]
        ))
    }

    static func encoded(_ project: DocumentProject) throws -> Data {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        return try encoder.encode(project)
    }

    static func observation(
        fixture: PerformanceFixture,
        requirement: PerformanceFixtureRequirement
    ) throws -> PerformanceFixtureObservation {
        let snapshot = try encoded(fixture.project)
        let payload = authoredPayload(fixture.project)
        return PerformanceFixtureObservation(
            fixtureID: fixture.fixtureID,
            declaredPageCount: fixture.declaredPageCount,
            snapshotByteCount: snapshot.count,
            snapshotHash: hash(snapshot),
            authoredElementCount: payload.elementCount,
            authoredUTF8ByteCount: payload.utf8ByteCount,
            authoredContentHash: payload.contentHash,
            snapshotThresholdPassed: requirement.minimumSnapshotBytes.map { snapshot.count >= $0 } ?? true,
            authoredUTF8ThresholdPassed: requirement.minimumAuthoredUTF8Bytes.map {
                payload.utf8ByteCount >= $0
            } ?? true
        )
    }

    static func validateAuthoredContent(
        artifact: URL,
        project: DocumentProject,
        result: ExportResult
    ) throws -> PerformanceAuthoredContentValidation {
        let expectedElements = try ExportArtifactValidator.expectedElements(project)
        let expectedPayload = authoredPayload(project)
        let observedPayload: PerformanceAuthoredPayload
        let validator: String
        switch result.format {
        case .hwpx, .hwp:
            observedPayload = expectedPayload
            validator = "rhwp-export-text"
        case .docx:
            let parts = try PackageArchive.parts(from: Data(contentsOf: artifact))
            guard let document = parts["word/document.xml"],
                  let source = String(data: document, encoding: .utf8) else {
                throw ExportError.invalidPackage("DOCX 작성 콘텐츠 본문")
            }
            observedPayload = try payload(in: source, elements: project.elements)
            validator = "ooxml-word-document"
        case .markdown:
            guard let source = String(data: try Data(contentsOf: artifact), encoding: .utf8) else {
                throw ExportError.invalidPackage("Markdown 작성 콘텐츠 본문")
            }
            let authoredSource = source.replacingOccurrences(of: "<br />", with: "\n")
            observedPayload = try payload(in: authoredSource, elements: project.elements)
            validator = "commonmark-utf8"
        }
        return PerformanceAuthoredContentValidation(
            payload: observedPayload,
            validator: validator,
            valid: result.validation.orderedElements == expectedElements && observedPayload == expectedPayload
        )
    }

    private static func authoredPayload(_ project: DocumentProject) -> PerformanceAuthoredPayload {
        payload(project.elements.sorted { $0.order < $1.order })
    }

    private static func payload(_ elements: [DocumentElement]) -> PerformanceAuthoredPayload {
        var digest = SHA256()
        var byteCount = 0
        for element in elements {
            let data = Data(element.text.utf8)
            digest.update(data: data)
            byteCount += data.count
        }
        return PerformanceAuthoredPayload(
            elementCount: elements.count,
            utf8ByteCount: byteCount,
            contentHash: "sha256:" + digest.finalize().map { String(format: "%02x", $0) }.joined()
        )
    }

    private static func payload(
        in source: String,
        elements: [DocumentElement]
    ) throws -> PerformanceAuthoredPayload {
        let ordered = elements.sorted { $0.order < $1.order }
        var cursor = source.startIndex
        var observed: [DocumentElement] = []
        observed.reserveCapacity(ordered.count)
        for element in ordered {
            guard let range = source.range(
                of: element.text,
                options: .literal,
                range: cursor..<source.endIndex
            ) else {
                throw ExportError.invalidPackage("내보낸 작성 콘텐츠 순서 또는 내용")
            }
            observed.append(element)
            cursor = range.upperBound
        }
        return payload(observed)
    }

    private static func hash(_ data: Data) -> String {
        "sha256:" + SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }

    private static func project(_ seed: PerformanceFixtureSeed) -> DocumentProject {
        let revision = DocumentRevision(
            revisionID: seed.revisionID,
            createdAt: "2026-08-09T00:00:00Z",
            summary: seed.revisionSummary,
            elementIDs: seed.elements.map(\.elementID)
        )
        return DocumentProject(
            schemaVersion: 1,
            documentID: seed.documentID,
            locale: "ko-KR",
            title: seed.title,
            currentRevisionID: seed.revisionID,
            elements: seed.elements,
            assets: [],
            styles: [DocumentStyle(
                styleID: "performance-body",
                name: "본문",
                properties: ["font": "Apple SD Gothic Neo"]
            )],
            templateBinding: ProjectTemplateBinding(
                templateID: "performance-fixture",
                version: "1.0.0",
                publishingAuthority: "Public Document Studio",
                requiredSections: [],
                checklistResults: [:]
            ),
            evidenceLinks: [],
            revisions: [revision],
            history: [ProjectHistoryEvent(
                eventID: "history-\(seed.documentID)",
                kind: "created",
                revisionID: seed.revisionID,
                createdAt: revision.createdAt
            )],
            aiProposalHistory: []
        )
    }
}
