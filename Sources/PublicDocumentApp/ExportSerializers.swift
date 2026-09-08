import CryptoKit
import Foundation

enum ExportSerializers {
    static func docx(project: DocumentProject) throws -> Data {
        let layout = try OfficialLayoutEngine.compile(project)
        let body = layout.blocks.map { block in
            let content = OfficialDocxEmit.content(block, profile: layout.profile)
            return "<w:sdt><w:sdtPr><w:tag w:val=\"\(xmlAttribute(block.elementID))\"/></w:sdtPr><w:sdtContent>\(content)</w:sdtContent></w:sdt>"
        }.joined()
        let manifestElements = layout.blocks.map {
            "<public-document-element element-id=\"\(xmlAttribute($0.elementID))\" kind=\"\(xmlAttribute($0.kind))\" order=\"\($0.order)\" text-hash=\"\(textHash($0.sourceText))\"/>"
        }.joined()
        let document = "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?><w:document xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\" xmlns:m=\"http://schemas.openxmlformats.org/officeDocument/2006/math\"><w:body>\(body)\(OfficialDocxEmit.sectPr(layout.profile))</w:body></w:document>"
        let customXML = "<?xml version=\"1.0\" encoding=\"UTF-8\"?><public-document-manifest xmlns=\"urn:public-document-studio\" document-id=\"\(xmlAttribute(project.documentID))\" revision-id=\"\(xmlAttribute(project.currentRevisionID))\" layout-profile-sha=\"\(xmlAttribute(layout.profile.sourceFingerprint))\">\(manifestElements)</public-document-manifest>"
        return try PackageArchive.data(parts: [
            PackagePart(path: "[Content_Types].xml", data: Data(contentTypesXML.utf8)),
            PackagePart(path: "_rels/.rels", data: Data("<?xml version=\"1.0\" encoding=\"UTF-8\"?><Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\"><Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\" Target=\"word/document.xml\"/></Relationships>".utf8)),
            PackagePart(path: "word/document.xml", data: Data(document.utf8)),
            PackagePart(path: "word/styles.xml", data: Data(OfficialDocxEmit.stylesXML(layout.profile).utf8)),
            PackagePart(path: "word/_rels/document.xml.rels", data: Data(documentRelationshipsXML.utf8)),
            PackagePart(path: "customXml/item1.xml", data: Data(customXML.utf8)),
            PackagePart(path: "customXml/itemProps1.xml", data: Data(customXMLPropertiesXML.utf8)),
            PackagePart(path: "customXml/_rels/item1.xml.rels", data: Data(customXMLRelationshipsXML.utf8)),
        ])
    }

    static func markdown(project: DocumentProject) throws -> Data {
        let elements = orderedElements(project.elements)
        let hasTitleHeading = elements.contains {
            $0.kind == "heading" && $0.text == project.title
        }
        var lines = hasTitleHeading ? [] : ["# \(commonMarkText(project.title))", ""]
        for element in elements {
            lines.append(marker(for: element))
            lines.append(contentsOf: try markdownLines(for: element, projectTitle: project.title))
            lines.append("")
        }
        return Data(lines.joined(separator: "\n").utf8)
    }

    static func markdownLines(for element: DocumentElement, projectTitle: String) throws -> [String] {
        switch element.kind {
        case "heading":
            let prefix = element.text == projectTitle ? "#" : "##"
            return ["\(prefix) \(commonMarkText(element.text))"]
        case "table", "approval-grid":
            let rows = try tableRows(element)
            guard let header = rows.first else { return [] }
            return [
                "<table>",
                "<thead><tr>\(header.map { "<th>\(htmlText($0))</th>" }.joined())</tr></thead>",
                "<tbody>",
            ] + rows.dropFirst().map {
                "<tr>\($0.map { "<td>\(htmlText($0))</td>" }.joined())</tr>"
            } + ["</tbody>", "</table>"]
        case "review-marker":
            return ["**\(commonMarkText(element.text))**"]
        case "metadata", "paragraph":
            let lines = OfficialTypeset.lines(element.text)
            if lines.count > 1 {
                return lines.map { commonMarkText($0) }
            }
            let normalized = element.text
                .replacingOccurrences(of: "\r\n", with: "\n")
                .replacingOccurrences(of: "\r", with: "\n")
            return normalized.split(
                separator: "\n",
                omittingEmptySubsequences: false
            ).map { commonMarkText(String($0)) }
        case "formula":
            throw ExportError.unsupportedElementKind(element.kind)
        default:
            throw ExportError.unsupportedElementKind(element.kind)
        }
    }

    private static func orderedElements(_ elements: [DocumentElement]) -> [DocumentElement] {
        elements.sorted {
            $0.order == $1.order ? $0.elementID < $1.elementID : $0.order < $1.order
        }
    }

    static func bindTableText(_ project: DocumentProject) throws -> DocumentProject {
        try project.replacingElements(project.elements.map { element in
            guard ["table", "approval-grid"].contains(element.kind), !element.contentHTML.isEmpty else {
                return element
            }
            let text = try tableRows(element).flatMap { $0 }.joined(separator: " ")
                .split(whereSeparator: \.isWhitespace).joined(separator: " ")
            return text == element.text ? element : element.replacingText(text)
        })
    }

    static func tableRows(_ element: DocumentElement) throws -> [[String]] {
        let document: XMLDocument
        do {
            document = try XMLDocument(
                xmlString: "<root>\(element.contentHTML)</root>",
                options: [.documentTidyHTML, .nodePreserveAll]
            )
        } catch {
            throw ExportError.invalidPackage("\(element.elementID) 표 셀을 읽을 수 없습니다")
        }
        let rows = try document.nodes(forXPath: "//tr").compactMap { node -> [String]? in
            guard let row = node as? XMLElement else { return nil }
            let cells = row.children?.compactMap { child -> String? in
                guard let cell = child as? XMLElement, ["td", "th"].contains(cell.name ?? "") else { return nil }
                return cell.stringValue?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            } ?? []
            return cells.isEmpty ? nil : cells
        }
        if !rows.isEmpty { return rows }
        let cells = try document.nodes(forXPath: "//span|//b").compactMap {
            $0.stringValue?.trimmingCharacters(in: .whitespacesAndNewlines)
        }
        guard cells.count >= 2 else {
            throw ExportError.invalidPackage("\(element.elementID) 표 셀을 읽을 수 없습니다")
        }
        let columnCount = cells.count.isMultiple(of: 3) ? 3 : 2
        return stride(from: 0, to: cells.count, by: columnCount).map {
            Array(cells[$0..<min($0 + columnCount, cells.count)])
        }
    }

    private static func xml(_ value: String) -> String {
        value
            .replacingOccurrences(of: "&", with: "&amp;")
            .replacingOccurrences(of: "<", with: "&lt;")
            .replacingOccurrences(of: ">", with: "&gt;")
            .replacingOccurrences(of: "\"", with: "&quot;")
            .replacingOccurrences(of: "'", with: "&apos;")
    }

    private static func htmlText(_ value: String) -> String {
        normalizedLineBreaks(value)
            .replacingOccurrences(of: "&", with: "&amp;")
            .replacingOccurrences(of: "<", with: "&lt;")
            .replacingOccurrences(of: ">", with: "&gt;")
            .replacingOccurrences(of: "\n", with: "<br />")
    }

    static func commonMarkText(_ value: String) -> String {
        var escaped = ""
        escaped.reserveCapacity(value.utf8.count)
        for scalar in normalizedLineBreaks(value).unicodeScalars {
            switch scalar.value {
            case 38: escaped.append(contentsOf: "&amp;")
            case 60: escaped.append(contentsOf: "&lt;")
            case 62: escaped.append(contentsOf: "&gt;")
            case 10: escaped.append(contentsOf: "<br />")
            case 33, 35, 40, 41, 42, 43, 45, 46, 61, 91, 92, 93, 95, 96, 123, 124, 125, 126:
                escaped.append("\\")
                escaped.unicodeScalars.append(scalar)
            default: escaped.unicodeScalars.append(scalar)
            }
        }
        return escaped
    }

    private static func marker(for element: DocumentElement) -> String {
        "<!-- public-document element-id=\"\(commentAttribute(element.elementID))\" kind=\"\(commentAttribute(element.kind))\" order=\"\(element.order)\" text-hash=\"\(textHash(element.text))\" -->"
    }

    private static func commentAttribute(_ value: String) -> String {
        xmlAttribute(value).replacingOccurrences(of: "--", with: "&#45;&#45;")
    }

    private static func xmlAttribute(_ value: String) -> String {
        xml(value)
            .replacingOccurrences(of: "\r", with: "&#13;")
            .replacingOccurrences(of: "\n", with: "&#10;")
            .replacingOccurrences(of: "\t", with: "&#9;")
    }

    private static func normalizedLineBreaks(_ value: String) -> String {
        guard value.contains("\r") else { return value }
        return value
            .replacingOccurrences(of: "\r\n", with: "\n")
            .replacingOccurrences(of: "\r", with: "\n")
    }

    private static func textHash(_ value: String) -> String {
        "sha256:" + SHA256.hash(data: Data(value.utf8)).map { String(format: "%02x", $0) }.joined()
    }

    private static let contentTypesXML = "<?xml version=\"1.0\" encoding=\"UTF-8\"?><Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\"><Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/><Default Extension=\"xml\" ContentType=\"application/xml\"/><Override PartName=\"/word/document.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml\"/><Override PartName=\"/word/styles.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml\"/><Override PartName=\"/customXml/item1.xml\" ContentType=\"application/xml\"/><Override PartName=\"/customXml/itemProps1.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.customXmlProperties+xml\"/></Types>"

    private static let documentRelationshipsXML = "<?xml version=\"1.0\" encoding=\"UTF-8\"?><Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\"><Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles\" Target=\"styles.xml\"/><Relationship Id=\"rId2\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/customXml\" Target=\"../customXml/item1.xml\"/></Relationships>"

    private static let customXMLRelationshipsXML = "<?xml version=\"1.0\" encoding=\"UTF-8\"?><Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\"><Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/customXmlProps\" Target=\"itemProps1.xml\"/></Relationships>"

    private static let customXMLPropertiesXML = "<?xml version=\"1.0\" encoding=\"UTF-8\"?><ds:datastoreItem ds:itemID=\"{94DB49B3-9D16-4AA7-872C-C156BCE7408B}\" xmlns:ds=\"http://schemas.openxmlformats.org/officeDocument/2006/customXml\"><ds:schemaRefs><ds:schemaRef ds:uri=\"urn:public-document-studio\"/></ds:schemaRefs></ds:datastoreItem>"

}
