import CryptoKit
import Foundation

struct ValidatedExportElement: Codable, Equatable {
    let elementID: String
    let kind: String
    let order: Int
    let textHash: String
}

struct FormatValidationReceipt: Codable {
    let structuralValid: Bool
    let semanticValid: Bool
    let evidenceSource: ExportEvidenceSource
    let validator: String
    let orderedElements: [ValidatedExportElement]
}

enum ExportArtifactValidator {
    static func validate(data: Data, format: DocumentFormat, project: DocumentProject) throws -> FormatValidationReceipt {
        let expected = try expectedElements(
            project,
            normalizeWhitespace: format == .hwpx || format == .hwp
        )
        let observed: [ValidatedExportElement]
        let validator: String

        switch format {
        case .hwpx, .hwp:
            observed = try RhwpExportAdapter().validate(data: data, format: format, project: project)
            validator = "rhwp artifact reopen + ordered text verification"
        case .docx:
            observed = try validateDOCX(data, project: project)
            validator = "artifact-derived OOXML graph + formula/table/content verification"
        case .markdown:
            observed = try validateMarkdown(data, project: project)
            validator = "artifact-derived CommonMark table + marker-bound content verification"
        }

        guard observed == expected else {
            throw ExportError.invalidPackage("\(format.rawValue) 요소 순서·종류·내용 해시가 원본 스냅샷과 다릅니다")
        }
        return FormatValidationReceipt(
            structuralValid: true, semanticValid: true, evidenceSource: .artifactDerived,
            validator: validator, orderedElements: observed
        )
    }

    static func expectedElements(
        _ project: DocumentProject,
        normalizeWhitespace: Bool = false
    ) throws -> [ValidatedExportElement] {
        let elements = project.elements.sorted { $0.order < $1.order }
        let ids = elements.map(\.elementID), orders = elements.map(\.order)
        guard Set(ids).count == ids.count,
              Set(orders).count == orders.count,
              !ids.contains(where: \.isEmpty) else {
            throw ExportError.invalidPackage("작성 요소 ID 또는 순서가 중복되었습니다")
        }
        return elements.map {
            let text = normalizeWhitespace
                ? $0.text.split(whereSeparator: \.isWhitespace).joined(separator: " ")
                : $0.text
            return ValidatedExportElement(
                elementID: $0.elementID, kind: $0.kind,
                order: $0.order, textHash: textHash(text)
            )
        }
    }

    private static func validateDOCX(_ data: Data, project: DocumentProject) throws -> [ValidatedExportElement] {
        guard data.starts(with: Data([0x50, 0x4b, 0x03, 0x04])) else {
            throw ExportError.invalidPackage("DOCX ZIP signature")
        }
        let parts = try PackageArchive.parts(from: data)
        let required = [
            "[Content_Types].xml", "_rels/.rels", "word/document.xml", "word/styles.xml",
            "word/_rels/document.xml.rels", "customXml/item1.xml", "customXml/itemProps1.xml",
            "customXml/_rels/item1.xml.rels",
        ]
        guard required.allSatisfy({ parts[$0]?.isEmpty == false }) else {
            throw ExportError.invalidPackage("DOCX 필수 OPC 파트")
        }
        guard let relationships = String(data: parts["word/_rels/document.xml.rels"]!, encoding: .utf8),
              relationships.contains("Target=\"styles.xml\""),
              relationships.contains("Target=\"../customXml/item1.xml\"") else {
            throw ExportError.invalidPackage("DOCX 관계 그래프")
        }
        guard let documentXML = String(data: parts["word/document.xml"]!, encoding: .utf8) else {
            throw ExportError.invalidPackage("DOCX document.xml UTF-8")
        }
        let document = try XMLDocument(xmlString: documentXML, options: .nodePreserveAll)
        try validateDOCXElements(document, project: project)
        let manifest = try XMLDocument(data: parts["customXml/item1.xml"]!, options: .nodePreserveAll)
        guard let root = manifest.rootElement(),
              root.name == "public-document-manifest",
              root.uri == "urn:public-document-studio",
              root.attribute(forName: "document-id")?.stringValue == project.documentID,
              root.attribute(forName: "revision-id")?.stringValue == project.currentRevisionID else {
            throw ExportError.invalidPackage("DOCX 요소 매니페스트 바인딩")
        }
        let recordXML = root.children?.compactMap { child -> String? in
            guard let element = child as? XMLElement, element.name == "public-document-element" else { return nil }
            return element.xmlString
        }.joined() ?? ""
        return try parseElements(in: Data(recordXML.utf8), tag: "public-document-element")
    }

    private static func validateDOCXElements(_ document: XMLDocument, project: DocumentProject) throws {
        let elements = project.elements.sorted { $0.order < $1.order }
        let controls = try document.nodes(forXPath: "//*[local-name()='sdt']")
        guard controls.count == elements.count else { throw ExportError.invalidPackage("DOCX 요소 콘텐츠 컨트롤") }
        for (control, element) in zip(controls, elements) {
            guard let properties = onlyChild(control, named: "sdtPr"),
                  let tag = onlyChild(properties, named: "tag") as? XMLElement,
                  tag.attributes?.first(where: { $0.localName == "val" })?.stringValue == element.elementID,
                  let content = onlyChild(control, named: "sdtContent")
            else { throw ExportError.invalidPackage("DOCX \(element.elementID) ID 바인딩") }
            let textNodes: [XMLNode]
            switch element.kind {
            case "table", "approval-grid":
                let rows = try ExportSerializers.tableRows(element)
                guard let table = onlyChild(content, named: "tbl"),
                      let grid = onlyChild(table, named: "tblGrid"),
                      children(grid, named: "gridCol").count == rows.map(\.count).max()
                else { throw ExportError.invalidPackage("DOCX \(element.elementID) 표 구조") }
                let artifactRows = children(table, named: "tr")
                let cells = artifactRows.flatMap { children($0, named: "tc") }
                guard artifactRows.count == rows.count,
                      cells.count == rows.flatMap({ $0 }).count,
                      artifactRows.first.flatMap({ onlyChild($0, named: "trPr") })
                        .flatMap({ onlyChild($0, named: "tblHeader") }) != nil
                else { throw ExportError.invalidPackage("DOCX \(element.elementID) 표 구조") }
                textNodes = descendants(table, named: "t")
            case "formula":
                guard let paragraph = onlyChild(content, named: "p"),
                      let math = onlyChild(paragraph, named: "oMath"),
                      let run = onlyChild(math, named: "r"),
                      let text = onlyChild(run, named: "t") else {
                    throw ExportError.invalidPackage("DOCX \(element.elementID) 수식 구조")
                }
                textNodes = [text]
            case "metadata", "heading", "paragraph", "review-marker":
                let paragraphs = children(content, named: "p")
                let heading = element.kind == "heading"
                    || element.styleID == "style-title"
                    || element.styleID == "style-section-heading"
                guard !paragraphs.isEmpty, !heading || paragraphs.count == 1 else {
                    throw ExportError.invalidPackage("DOCX \(element.elementID) 문단 구조")
                }
                textNodes = paragraphs.flatMap { descendants($0, named: "t") }
            default:
                throw ExportError.unsupportedElementKind(element.kind)
            }
            let actualText = textNodes.compactMap(\.stringValue).joined(separator: " ")
                .split(whereSeparator: \.isWhitespace).joined(separator: " ")
            let expectedText = element.text.split(whereSeparator: \.isWhitespace).joined(separator: " ")
            let typesetLines = OfficialTypeset.lines(element.text)
            let preservesExactWhitespace = !["table", "approval-grid", "formula"].contains(element.kind)
                && typesetLines.count <= 1
            let exactText = try content.nodes(
                forXPath: ".//*[local-name()='t' or local-name()='br' or local-name()='tab']"
            ).map { node in
                switch node.localName {
                case "br": return "\n"
                case "tab": return "\t"
                default: return node.stringValue ?? ""
                }
            }.joined()
            let normalizedExpected = element.text
                .replacingOccurrences(of: "\r\n", with: "\n")
                .replacingOccurrences(of: "\r", with: "\n")
            guard preservesExactWhitespace
                ? exactText == normalizedExpected
                : actualText == expectedText
            else {
                throw ExportError.invalidPackage("DOCX \(element.elementID) 본문 바인딩")
            }
        }
    }

    private static func validateMarkdown(_ data: Data, project: DocumentProject) throws -> [ValidatedExportElement] {
        guard let markdown = String(data: data, encoding: .utf8), !markdown.isEmpty else {
            throw ExportError.invalidPackage("Markdown UTF-8")
        }
        let marker = #"<!--\s+public-document\s+([^>]+?)\s*-->"#
        let expression = try NSRegularExpression(pattern: marker)
        let range = NSRange(markdown.startIndex..<markdown.endIndex, in: markdown)
        let matches = expression.matches(in: markdown, range: range)
        let elements = project.elements.sorted { $0.order < $1.order }
        guard matches.count == elements.count else { throw ExportError.invalidPackage("Markdown 요소 표식 수") }
        let firstMarker = matches.first.flatMap { Range($0.range, in: markdown)?.lowerBound }
            ?? markdown.endIndex
        let preamble = markdown[..<firstMarker].trimmingCharacters(in: .whitespacesAndNewlines)
        let hasTitleHeading = elements.contains { $0.kind == "heading" && $0.text == project.title }
        let expectedPreamble = hasTitleHeading ? "" : "# \(ExportSerializers.commonMarkText(project.title))"
        guard preamble == expectedPreamble else {
            throw ExportError.invalidPackage("Markdown 제목 머리말")
        }
        for (index, match) in matches.enumerated() {
            guard let segmentStart = Range(match.range, in: markdown)?.upperBound else {
                throw ExportError.invalidPackage("Markdown 요소 표식 범위")
            }
            let nextStart = matches.dropFirst(index + 1).first.flatMap {
                Range($0.range, in: markdown)?.lowerBound
            } ?? markdown.endIndex
            let actual = markdown[segmentStart..<nextStart]
                .trimmingCharacters(in: .whitespacesAndNewlines)
            let expected = try ExportSerializers.markdownLines(
                for: elements[index],
                projectTitle: project.title
            ).joined(separator: "\n")
            guard actual == expected else {
                throw ExportError.invalidPackage("Markdown \(elements[index].elementID) 표식 본문")
            }
        }
        return try parseElements(matches: matches, in: markdown)
    }

    private static func children(_ node: XMLNode, named name: String) -> [XMLNode] {
        node.children?.filter { $0.localName == name } ?? []
    }

    private static func onlyChild(_ node: XMLNode, named name: String) -> XMLNode? {
        let matches = children(node, named: name)
        return matches.count == 1 ? matches[0] : nil
    }

    private static func descendants(_ node: XMLNode, named name: String) -> [XMLNode] {
        (node.children ?? []).flatMap { child in
            (child.localName == name ? [child] : []) + descendants(child, named: name)
        }
    }

    private static func parseElements(in data: Data, tag: String) throws -> [ValidatedExportElement] {
        let pattern = #"<"# + NSRegularExpression.escapedPattern(for: tag) + #"\s+([^>]+?)/?>"#
        return try parseElements(in: data, pattern: pattern)
    }

    private static func parseElements(in data: Data, pattern: String) throws -> [ValidatedExportElement] {
        guard let source = String(data: data, encoding: .utf8) else {
            throw ExportError.invalidPackage("요소 매니페스트 UTF-8")
        }
        let expression = try NSRegularExpression(pattern: pattern)
        let fullRange = NSRange(source.startIndex..<source.endIndex, in: source)
        return try expression.matches(in: source, range: fullRange).map { match in
            guard let attributesRange = Range(match.range(at: 1), in: source) else {
                throw ExportError.invalidPackage("요소 매니페스트 속성")
            }
            let attributes = String(source[attributesRange])
            let values = try attributeValues(attributes)
            guard
                let elementID = values["element-id"],
                let kind = values["kind"],
                let orderText = values["order"],
                let order = Int(orderText),
                let textHash = values["text-hash"]
            else {
                throw ExportError.invalidPackage("요소 매니페스트 필드")
            }
            return ValidatedExportElement(
                elementID: xmlUnescape(elementID),
                kind: xmlUnescape(kind),
                order: order,
                textHash: xmlUnescape(textHash)
            )
        }
    }

    private static func parseElements(
        matches: [NSTextCheckingResult],
        in source: String
    ) throws -> [ValidatedExportElement] {
        try matches.map { match in
            guard let attributesRange = Range(match.range(at: 1), in: source) else {
                throw ExportError.invalidPackage("요소 매니페스트 속성")
            }
            let values = try attributeValues(String(source[attributesRange]))
            guard
                let elementID = values["element-id"],
                let kind = values["kind"],
                let orderText = values["order"],
                let order = Int(orderText),
                let textHash = values["text-hash"]
            else {
                throw ExportError.invalidPackage("요소 매니페스트 필드")
            }
            return ValidatedExportElement(
                elementID: xmlUnescape(elementID),
                kind: xmlUnescape(kind),
                order: order,
                textHash: xmlUnescape(textHash)
            )
        }
    }

    private static func attributeValues(_ source: String) throws -> [String: String] {
        let expression = try NSRegularExpression(pattern: #"([a-z-]+)=\"([^\"]*)\""#)
        let range = NSRange(source.startIndex..<source.endIndex, in: source)
        return expression.matches(in: source, range: range).reduce(into: [:]) { values, match in
            guard
                let nameRange = Range(match.range(at: 1), in: source),
                let valueRange = Range(match.range(at: 2), in: source)
            else { return }
            values[String(source[nameRange])] = String(source[valueRange])
        }
    }

    private static func xmlUnescape(_ source: String) -> String {
        source
            .replacingOccurrences(of: "&#45;", with: "-")
            .replacingOccurrences(of: "&#10;", with: "\n")
            .replacingOccurrences(of: "&#13;", with: "\r")
            .replacingOccurrences(of: "&#9;", with: "\t")
            .replacingOccurrences(of: "&quot;", with: "\"")
            .replacingOccurrences(of: "&apos;", with: "'")
            .replacingOccurrences(of: "&lt;", with: "<")
            .replacingOccurrences(of: "&gt;", with: ">")
            .replacingOccurrences(of: "&amp;", with: "&")
    }

    private static func textHash(_ text: String) -> String {
        "sha256:" + SHA256.hash(data: Data(text.utf8)).map { String(format: "%02x", $0) }.joined()
    }
}
