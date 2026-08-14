import CryptoKit
import Foundation

enum ExportSerializers {
    static func docx(project: DocumentProject) throws -> Data {
        let elements = orderedElements(project.elements)
        let body = try elements.map { element in
            let content = try docxElement(element)
            return "<w:sdt><w:sdtPr><w:tag w:val=\"\(xmlAttribute(element.elementID))\"/></w:sdtPr><w:sdtContent>\(content)</w:sdtContent></w:sdt>"
        }.joined()
        let manifestElements = elements.map {
            "<public-document-element element-id=\"\(xmlAttribute($0.elementID))\" kind=\"\(xmlAttribute($0.kind))\" order=\"\($0.order)\" text-hash=\"\(textHash($0.text))\"/>"
        }.joined()
        let document = "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?><w:document xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\" xmlns:m=\"http://schemas.openxmlformats.org/officeDocument/2006/math\"><w:body>\(body)<w:sectPr><w:pgSz w:w=\"11906\" w:h=\"16838\"/><w:pgMar w:top=\"1440\" w:right=\"1440\" w:bottom=\"1440\" w:left=\"1440\" w:header=\"720\" w:footer=\"720\" w:gutter=\"0\"/></w:sectPr></w:body></w:document>"
        let customXML = "<?xml version=\"1.0\" encoding=\"UTF-8\"?><public-document-manifest xmlns=\"urn:public-document-studio\" document-id=\"\(xmlAttribute(project.documentID))\" revision-id=\"\(xmlAttribute(project.currentRevisionID))\">\(manifestElements)</public-document-manifest>"
        return try PackageArchive.data(parts: [
            PackagePart(path: "[Content_Types].xml", data: Data(contentTypesXML.utf8)),
            PackagePart(path: "_rels/.rels", data: Data("<?xml version=\"1.0\" encoding=\"UTF-8\"?><Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\"><Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\" Target=\"word/document.xml\"/></Relationships>".utf8)),
            PackagePart(path: "word/document.xml", data: Data(document.utf8)),
            PackagePart(path: "word/styles.xml", data: Data(stylesXML.utf8)),
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
            return [commonMarkText(element.text)]
        case "formula":
            throw ExportError.unsupportedElementKind(element.kind)
        default:
            throw ExportError.unsupportedElementKind(element.kind)
        }
    }

    static func docxElement(_ element: DocumentElement) throws -> String {
        switch element.kind {
        case "table", "approval-grid":
            let table = try tableRows(element)
            let columnCount = table.map(\.count).max() ?? 1
            let columnWidth = max(1, 9_000 / columnCount)
            let grid = (0..<columnCount).map { _ in
                "<w:gridCol w:w=\"\(columnWidth)\"/>"
            }.joined()
            let rows = table.enumerated().map { rowIndex, row in
                let rowProperties = rowIndex == 0 ? "<w:trPr><w:tblHeader w:val=\"true\"/></w:trPr>" : ""
                let cells = row.map { cell in
                    "<w:tc><w:tcPr><w:tcW w:w=\"\(columnWidth)\" w:type=\"dxa\"/></w:tcPr><w:p><w:r><w:t xml:space=\"preserve\">\(xml(cell))</w:t></w:r></w:p></w:tc>"
                }.joined()
                return "<w:tr>\(rowProperties)\(cells)</w:tr>"
            }.joined()
            return "<w:tbl><w:tblPr><w:tblStyle w:val=\"TableGrid\"/><w:tblW w:w=\"0\" w:type=\"auto\"/><w:tblLayout w:type=\"fixed\"/><w:tblLook w:val=\"04A0\" w:firstRow=\"1\" w:lastRow=\"0\" w:firstColumn=\"1\" w:lastColumn=\"0\" w:noHBand=\"0\" w:noVBand=\"1\"/></w:tblPr><w:tblGrid>\(grid)</w:tblGrid>\(rows)</w:tbl>"
        case "formula":
            return "<w:p><m:oMath><m:r><m:t>\(xml(element.text))</m:t></m:r></m:oMath></w:p>"
        case "metadata", "heading", "paragraph", "review-marker":
            let paragraphStyle: String
            if element.styleID == "style-title" || (element.kind == "heading" && element.elementID == "element-title") {
                paragraphStyle = "<w:pPr><w:pStyle w:val=\"Title\"/></w:pPr>"
            } else if element.kind == "heading" || element.styleID == "style-section-heading" {
                paragraphStyle = "<w:pPr><w:pStyle w:val=\"Heading2\"/></w:pPr>"
            } else if element.styleID == "style-reference" || element.styleID == "style-reference-note" || element.styleID == "style-annotation" {
                paragraphStyle = "<w:pPr><w:pStyle w:val=\"IntenseQuote\"/></w:pPr>"
            } else {
                paragraphStyle = ""
            }
            return "<w:p>\(paragraphStyle)<w:r><w:t xml:space=\"preserve\">\(xml(element.text))</w:t></w:r></w:p>"
        default:
            throw ExportError.unsupportedElementKind(element.kind)
        }
    }

    private static func orderedElements(_ elements: [DocumentElement]) -> [DocumentElement] {
        elements.sorted {
            $0.order == $1.order ? $0.elementID < $1.elementID : $0.order < $1.order
        }
    }

    static func tableRows(_ element: DocumentElement) throws -> [[String]] {
        let document = try XMLDocument(xmlString: "<root>\(element.contentHTML)</root>", options: .nodePreserveAll)
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
        for character in normalizedLineBreaks(value) {
            switch character {
            case "&": escaped += "&amp;"
            case "<": escaped += "&lt;"
            case ">": escaped += "&gt;"
            case "\n": escaped += "<br />"
            case "\\", "`", "*", "_", "{", "}", "[", "]", "(", ")", "#", "+", "-", ".", "!", "|", "~", "=":
                escaped += "\\\(character)"
            default:
                escaped.append(character)
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
        value
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

    private static let stylesXML = "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?><w:styles xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\"><w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii=\"Apple Myungjo\" w:eastAsia=\"Apple Myungjo\" w:hAnsi=\"Apple Myungjo\"/><w:sz w:val=\"30\"/><w:szCs w:val=\"30\"/><w:lang w:val=\"ko-KR\" w:eastAsia=\"ko-KR\"/></w:rPr></w:rPrDefault><w:pPrDefault><w:pPr><w:spacing w:line=\"360\" w:lineRule=\"auto\"/></w:pPr></w:pPrDefault></w:docDefaults><w:style w:type=\"paragraph\" w:default=\"1\" w:styleId=\"Normal\"><w:name w:val=\"Normal\"/><w:qFormat/></w:style><w:style w:type=\"paragraph\" w:styleId=\"Title\"><w:name w:val=\"Title\"/><w:basedOn w:val=\"Normal\"/><w:next w:val=\"Normal\"/><w:qFormat/><w:pPr><w:keepNext/><w:jc w:val=\"center\"/></w:pPr><w:rPr><w:rFonts w:ascii=\"Apple SD Gothic Neo\" w:eastAsia=\"Apple SD Gothic Neo\" w:hAnsi=\"Apple SD Gothic Neo\"/><w:b/><w:sz w:val=\"32\"/><w:szCs w:val=\"32\"/></w:rPr></w:style><w:style w:type=\"paragraph\" w:styleId=\"Heading2\"><w:name w:val=\"Heading 2\"/><w:basedOn w:val=\"Normal\"/><w:qFormat/><w:rPr><w:rFonts w:ascii=\"Apple SD Gothic Neo\" w:eastAsia=\"Apple SD Gothic Neo\" w:hAnsi=\"Apple SD Gothic Neo\"/><w:b/><w:sz w:val=\"32\"/><w:szCs w:val=\"32\"/></w:rPr></w:style><w:style w:type=\"paragraph\" w:styleId=\"IntenseQuote\"><w:name w:val=\"Intense Quote\"/><w:basedOn w:val=\"Normal\"/><w:qFormat/><w:rPr><w:rFonts w:ascii=\"Apple SD Gothic Neo\" w:eastAsia=\"Apple SD Gothic Neo\" w:hAnsi=\"Apple SD Gothic Neo\"/><w:sz w:val=\"24\"/><w:szCs w:val=\"24\"/></w:rPr></w:style><w:style w:type=\"table\" w:styleId=\"TableGrid\"><w:name w:val=\"Table Grid\"/><w:uiPriority w:val=\"59\"/><w:tblPr><w:tblBorders><w:top w:val=\"single\" w:sz=\"4\" w:space=\"0\" w:color=\"auto\"/><w:left w:val=\"single\" w:sz=\"4\" w:space=\"0\" w:color=\"auto\"/><w:bottom w:val=\"single\" w:sz=\"4\" w:space=\"0\" w:color=\"auto\"/><w:right w:val=\"single\" w:sz=\"4\" w:space=\"0\" w:color=\"auto\"/><w:insideH w:val=\"single\" w:sz=\"4\" w:space=\"0\" w:color=\"auto\"/><w:insideV w:val=\"single\" w:sz=\"4\" w:space=\"0\" w:color=\"auto\"/></w:tblBorders></w:tblPr></w:style></w:styles>"
}
