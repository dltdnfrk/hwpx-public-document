import CryptoKit
import Foundation

/// Typesetting generation engine for public documents.
/// Compiles guidebook toolkit + print tokens + statutory list rules into a layout IR.
/// GenOffice remains the editor UI / OPC normalizer. rhwp remains the HWPX package writer.
enum OfficialLayoutEngine {
    static func compile(_ project: DocumentProject) throws -> OfficialLayout {
        let profile = try OfficialDocumentProfile.load()
        let elements = project.elements.sorted {
            $0.order == $1.order ? $0.elementID < $1.elementID : $0.order < $1.order
        }
        let blocks = try elements.map { element -> OfficialLayoutBlock in
            switch element.kind {
            case "table", "approval-grid":
                return OfficialLayoutBlock(
                    elementID: element.elementID,
                    kind: element.kind,
                    order: element.order,
                    sourceText: element.text,
                    payload: .table(try ExportSerializers.tableRows(element))
                )
            case "formula":
                return OfficialLayoutBlock(
                    elementID: element.elementID,
                    kind: element.kind,
                    order: element.order,
                    sourceText: element.text,
                    payload: .formula(element.text)
                )
            default:
                return OfficialLayoutBlock(
                    elementID: element.elementID,
                    kind: element.kind,
                    order: element.order,
                    sourceText: element.text,
                    payload: .lines(lines(for: element, profile: profile))
                )
            }
        }
        return OfficialLayout(profile: profile, project: project, blocks: blocks)
    }

    private static func lines(for element: DocumentElement, profile: OfficialDocumentProfile) -> [OfficialLayoutLine] {
        let heading = element.kind == "heading"
            || element.styleID == "style-title"
            || element.styleID == "style-section-heading"
        let presetID: String
        if element.styleID == "style-title" || (element.kind == "heading" && element.elementID == "element-title") {
            presetID = "style-title"
        } else if heading {
            presetID = "style-section-heading"
        } else if ["style-reference", "style-reference-note", "style-annotation"].contains(element.styleID) {
            presetID = "style-reference-note"
        } else {
            presetID = "style-body"
        }
        let preset = profile.presets[presetID]
        let style = preset?.docxStyleId ?? "Normal"
        let typesetLines = heading ? [element.text] : OfficialTypeset.lines(element.text)
        let texts = !heading && typesetLines.count > 1 ? typesetLines : [element.text]
        return (texts.isEmpty ? [element.text] : texts).map { line in
            let lineStyle = heading ? style : OfficialTypeset.paragraphStyle(for: line, fallback: style)
            let hang = heading ? nil : OfficialTypeset.hanging(line)
            let spacingBefore: Int
            let spacingAfter: Int
            if heading && style == "Title" {
                spacingBefore = 0
                spacingAfter = 200
            } else if heading {
                spacingBefore = 280
                spacingAfter = 60
            } else {
                spacingBefore = 0
                spacingAfter = 80
            }
            return OfficialLayoutLine(
                text: line,
                styleId: lineStyle,
                hanging: hang,
                align: element.styleID == "style-end-mark"
                    ? "right"
                    : preset?.align == "left" ? nil : preset?.align,
                spacingBefore: spacingBefore,
                spacingAfter: spacingAfter,
                keepNext: heading,
                letterSpacing: profile.letterSpacingTwips
            )
        }
    }
}

struct OfficialLayout {
    let profile: OfficialDocumentProfile
    let project: DocumentProject
    let blocks: [OfficialLayoutBlock]
}

struct OfficialLayoutBlock {
    let elementID: String
    let kind: String
    let order: Int
    let sourceText: String
    let payload: Payload

    enum Payload {
        case lines([OfficialLayoutLine])
        case table([[String]])
        case formula(String)
    }
}

struct OfficialLayoutLine {
    let text: String
    let styleId: String
    let hanging: (left: Int, hanging: Int)?
    let align: String?
    let spacingBefore: Int
    let spacingAfter: Int
    let keepNext: Bool
    let letterSpacing: Int
}

struct OfficialDocumentProfile {
    struct Page {
        let widthTwips: Int
        let heightTwips: Int
        let top: Int
        let right: Int
        let bottom: Int
        let left: Int
        let header: Int
        let footer: Int
    }

    struct Preset {
        let styleID: String
        let docxStyleId: String
        let hangulFont: String
        let macFont: String
        let wordFont: String
        let pointSize: Int
        let bold: Bool
        let align: String
    }

    let page: Page
    let presets: [String: Preset]
    let presetIDs: [String]
    let bodyFont: String
    let guidebookList: [String]
    let statutoryList: [String]
    let letterSpacingHwp: Int
    let letterSpacingTwips: Int
    let contentWidthTwips: Int
    let sourceFingerprint: String
    let hwpxTop: Int
    let hwpxRight: Int
    let hwpxBottom: Int
    let hwpxLeft: Int

    static func load() throws -> OfficialDocumentProfile {
        let toolkitURL = try requiredResource("Templates/official-style-toolkit-1.0.0.json")
        let tokenURL = try requiredResource("Print/print-tokens-1.0.0.json")
        return try load(toolkitURL: toolkitURL, tokenURL: tokenURL)
    }

    static func load(toolkitURL: URL, tokenURL: URL) throws -> OfficialDocumentProfile {
        let toolkitData = try Data(contentsOf: toolkitURL)
        let tokenData = try Data(contentsOf: tokenURL)
        guard let toolkit = try JSONSerialization.jsonObject(with: toolkitData) as? [String: Any],
              let tokens = try JSONSerialization.jsonObject(with: tokenData) as? [String: Any]
        else {
            throw ExportError.invalidPackage("official layout profile must contain JSON objects")
        }
        guard toolkit["schemaVersion"] as? Int == 1,
              tokens["schemaVersion"] as? Int == 1,
              let toolkitID = nonEmpty(toolkit["toolkitID"]),
              let tokenID = nonEmpty(tokens["tokenID"]),
              let pageJSON = tokens["page"] as? [String: Any],
              pageJSON["paper"] as? String == "a4",
              let margin = pageJSON["marginMm"] as? [String: Any],
              let topMM = positiveDouble(margin["top"]),
              let rightMM = positiveDouble(margin["right"]),
              let bottomMM = positiveDouble(margin["bottom"]),
              let leftMM = positiveDouble(margin["left"]),
              topMM < 297,
              bottomMM < 297,
              rightMM < 210,
              leftMM < 210,
              let presetsJSON = toolkit["presets"] as? [String: Any]
        else {
            throw ExportError.invalidPackage("official layout profile has invalid schema, page, or margins")
        }
        let top = mmToTwips(topMM)
        let right = mmToTwips(rightMM)
        let bottom = mmToTwips(bottomMM)
        let left = mmToTwips(leftMM)
        guard left + right < 11906,
              top + bottom < 16838 else {
            throw ExportError.invalidPackage(
                "official layout profile margins leave no positive page content area"
            )
        }
        var presets: [String: Preset] = [:]
        for (_, value) in presetsJSON {
            guard let item = value as? [String: Any],
                  let styleID = nonEmpty(item["styleID"]),
                  let docxStyleID = nonEmpty(item["docxStyleId"]),
                  let hangulFont = nonEmpty(item["hangulFont"]),
                  let macFont = nonEmpty(item["macFont"]),
                  let pointSize = item["pointSize"] as? Int,
                  (1...1000).contains(pointSize),
                  let bold = item["bold"] as? Bool,
                  let align = nonEmpty(item["align"])
            else {
                throw ExportError.invalidPackage("official layout profile contains an invalid preset")
            }
            presets[styleID] = Preset(
                styleID: styleID,
                docxStyleId: docxStyleID,
                hangulFont: hangulFont,
                macFont: macFont,
                wordFont: wordFont(macFont),
                pointSize: pointSize,
                bold: bold,
                align: align
            )
        }
        let requiredStyles = [
            "style-title",
            "style-section-heading",
            "style-body",
            "style-body-detail",
            "style-reference-note",
            "style-annotation",
            "style-reference",
        ]
        guard requiredStyles.allSatisfy({ presets[$0] != nil }),
              let presetIDs = stringList(toolkit["presetOrder"]),
              presetIDs == requiredStyles,
              let guidebookList = stringList(toolkit["guidebookList"]),
              let statutoryList = stringList(toolkit["statutoryList"]),
              let hwpSpacing = ((toolkit["operations"] as? [String: Any])?["word-keep"] as? [String: Any])?["letterSpacing"] as? Int,
              (-100...100).contains(hwpSpacing),
              let body = presets["style-body"]
        else {
            throw ExportError.invalidPackage("official layout profile is missing required presets or letter spacing")
        }
        var fingerprintInput = Data(toolkitID.utf8)
        fingerprintInput.append(0)
        fingerprintInput.append(toolkitData)
        fingerprintInput.append(0)
        fingerprintInput.append(Data(tokenID.utf8))
        fingerprintInput.append(0)
        fingerprintInput.append(tokenData)
        let fingerprint = SHA256.hash(data: fingerprintInput)
            .map { String(format: "%02x", $0) }.joined()
        return OfficialDocumentProfile(
            page: Page(widthTwips: 11906, heightTwips: 16838, top: top, right: right, bottom: bottom, left: left, header: 720, footer: 720),
            presets: presets,
            presetIDs: presetIDs,
            bodyFont: body.wordFont,
            guidebookList: guidebookList,
            statutoryList: statutoryList,
            letterSpacingHwp: hwpSpacing,
            letterSpacingTwips: letterSpacingTwips(pointSize: body.pointSize, hwp: hwpSpacing),
            contentWidthTwips: 11906 - left - right,
            sourceFingerprint: "sha256:\(fingerprint)",
            hwpxTop: mmToHwpx(topMM),
            hwpxRight: mmToHwpx(rightMM),
            hwpxBottom: mmToHwpx(bottomMM),
            hwpxLeft: mmToHwpx(leftMM)
        )
    }

    private static func resource(_ relative: String) -> URL? {
        if let bundled = Bundle.main.resourceURL?.appendingPathComponent(relative),
           FileManager.default.fileExists(atPath: bundled.path) {
            return bundled
        }
        let cwd = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
            .appendingPathComponent("Resources")
            .appendingPathComponent(relative)
        if FileManager.default.fileExists(atPath: cwd.path) { return cwd }
        return nil
    }

    private static func requiredResource(_ relative: String) throws -> URL {
        guard let url = resource(relative) else {
            throw ExportError.invalidPackage("official layout profile resource is missing: \(relative)")
        }
        return url
    }

    private static func wordFont(_ macFont: String) -> String {
        macFont == "AppleMyungjo" ? "Apple Myungjo" : macFont
    }

    private static func nonEmpty(_ value: Any?) -> String? {
        guard let text = value as? String, !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            return nil
        }
        return text
    }

    private static func positiveDouble(_ value: Any?) -> Double? {
        let number: Double?
        if let value = value as? Double {
            number = value
        } else if let value = value as? Int {
            number = Double(value)
        } else {
            number = nil
        }
        guard let number, number.isFinite, number > 0 else { return nil }
        return number
    }

    private static func stringList(_ value: Any?) -> [String]? {
        guard let values = value as? [String],
              !values.isEmpty,
              values.allSatisfy({ !$0.isEmpty })
        else {
            return nil
        }
        return values
    }

    static func mmToTwips(_ mm: Double) -> Int {
        Int((mm * 1440.0 / 25.4).rounded())
    }

    static func mmToHwpx(_ mm: Double) -> Int {
        Int((mm * 283.465).rounded())
    }

    static func letterSpacingTwips(pointSize: Int, hwp: Int) -> Int {
        Int((Double(pointSize) * 20.0 * Double(hwp) / 100.0).rounded())
    }
}

enum OfficialDocxEmit {
    static func content(_ block: OfficialLayoutBlock, profile: OfficialDocumentProfile) -> String {
        switch block.payload {
        case .table(let rows):
            return table(rows, profile: profile)
        case .formula(let text):
            return "<w:p><m:oMath><m:r><m:t xml:space=\"preserve\">\(xml(text))</m:t></m:r></m:oMath></w:p>"
        case .lines(let lines):
            return lines.map(paragraph).joined()
        }
    }

    static func sectPr(_ profile: OfficialDocumentProfile) -> String {
        let page = profile.page
        return "<w:sectPr><w:pgSz w:w=\"\(page.widthTwips)\" w:h=\"\(page.heightTwips)\"/><w:pgMar w:top=\"\(page.top)\" w:right=\"\(page.right)\" w:bottom=\"\(page.bottom)\" w:left=\"\(page.left)\" w:header=\"\(page.header)\" w:footer=\"\(page.footer)\" w:gutter=\"0\"/></w:sectPr>"
    }

    static func stylesXML(_ profile: OfficialDocumentProfile) -> String {
        let title = profile.presets["style-title"]
        let heading = profile.presets["style-section-heading"]
        let quote = profile.presets["style-reference-note"]
        let bodySz = halfPoints(profile.presets["style-body"]?.pointSize ?? 15)
        return "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?><w:styles xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\"><w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii=\"\(xml(profile.bodyFont))\" w:eastAsia=\"\(xml(profile.bodyFont))\" w:hAnsi=\"\(xml(profile.bodyFont))\"/><w:spacing w:val=\"\(profile.letterSpacingTwips)\"/><w:sz w:val=\"\(bodySz)\"/><w:szCs w:val=\"\(bodySz)\"/><w:lang w:val=\"ko-KR\" w:eastAsia=\"ko-KR\"/></w:rPr></w:rPrDefault><w:pPrDefault><w:pPr><w:spacing w:line=\"360\" w:lineRule=\"auto\"/></w:pPr></w:pPrDefault></w:docDefaults><w:style w:type=\"paragraph\" w:default=\"1\" w:styleId=\"Normal\"><w:name w:val=\"Normal\"/><w:qFormat/></w:style>"
            + paragraphStyle(id: "Title", name: "Title", preset: title, keepNext: true, before: 0, after: 200, letterSpacing: profile.letterSpacingTwips)
            + paragraphStyle(id: "Heading2", name: "Heading 2", preset: heading, keepNext: true, before: 280, after: 60, letterSpacing: profile.letterSpacingTwips)
            + paragraphStyle(id: "IntenseQuote", name: "Intense Quote", preset: quote, keepNext: false, before: 0, after: 0, letterSpacing: profile.letterSpacingTwips)
            + "<w:style w:type=\"table\" w:styleId=\"TableGrid\"><w:name w:val=\"Table Grid\"/><w:uiPriority w:val=\"59\"/><w:tblPr><w:tblBorders><w:top w:val=\"single\" w:sz=\"4\" w:space=\"0\" w:color=\"auto\"/><w:left w:val=\"single\" w:sz=\"4\" w:space=\"0\" w:color=\"auto\"/><w:bottom w:val=\"single\" w:sz=\"4\" w:space=\"0\" w:color=\"auto\"/><w:right w:val=\"single\" w:sz=\"4\" w:space=\"0\" w:color=\"auto\"/><w:insideH w:val=\"single\" w:sz=\"4\" w:space=\"0\" w:color=\"auto\"/><w:insideV w:val=\"single\" w:sz=\"4\" w:space=\"0\" w:color=\"auto\"/></w:tblBorders></w:tblPr></w:style></w:styles>"
    }

    private static func paragraphStyle(
        id: String,
        name: String,
        preset: OfficialDocumentProfile.Preset?,
        keepNext: Bool,
        before: Int,
        after: Int,
        letterSpacing: Int
    ) -> String {
        let font = xml(preset?.wordFont ?? "Apple SD Gothic Neo")
        let sz = halfPoints(preset?.pointSize ?? 16)
        let bold = preset?.bold == true ? "<w:b/>" : ""
        let keep = keepNext ? "<w:keepNext/>" : ""
        let alignment = preset?.align ?? "left"
        let jc = alignment == "left" ? "" : "<w:jc w:val=\"\(xml(alignment))\"/>"
        let spacing = (before > 0 || after > 0)
            ? "<w:spacing w:before=\"\(before)\" w:after=\"\(after)\"/>"
            : ""
        return "<w:style w:type=\"paragraph\" w:styleId=\"\(id)\"><w:name w:val=\"\(name)\"/><w:basedOn w:val=\"Normal\"/><w:qFormat/><w:pPr>\(keep)\(spacing)\(jc)</w:pPr><w:rPr><w:rFonts w:ascii=\"\(font)\" w:eastAsia=\"\(font)\" w:hAnsi=\"\(font)\"/>\(bold)<w:spacing w:val=\"\(letterSpacing)\"/><w:sz w:val=\"\(sz)\"/><w:szCs w:val=\"\(sz)\"/></w:rPr></w:style>"
    }

    private static func paragraph(_ line: OfficialLayoutLine) -> String {
        let indent = line.hanging.map { "<w:ind w:left=\"\($0.left)\" w:hanging=\"\($0.hanging)\"/>" } ?? ""
        let align = line.align.map { "<w:jc w:val=\"\($0)\"/>" } ?? ""
        var spacing = ""
        if line.spacingBefore > 0 || line.spacingAfter > 0 {
            let before = line.spacingBefore > 0 ? " w:before=\"\(line.spacingBefore)\"" : ""
            let after = line.spacingAfter > 0 ? " w:after=\"\(line.spacingAfter)\"" : ""
            spacing = "<w:spacing\(before)\(after)/>"
        }
        let keep = line.keepNext ? "<w:keepNext/>" : ""
        return "<w:p><w:pPr><w:pStyle w:val=\"\(xml(line.styleId))\"/>\(keep)\(spacing)\(indent)\(align)</w:pPr><w:r><w:rPr><w:spacing w:val=\"\(line.letterSpacing)\"/></w:rPr>\(wordText(line.text))</w:r></w:p>"
    }

    private static func wordText(_ value: String) -> String {
        let normalized = value.contains("\r")
            ? value
                .replacingOccurrences(of: "\r\n", with: "\n")
                .replacingOccurrences(of: "\r", with: "\n")
            : value
        return "<w:t xml:space=\"preserve\">\(xml(normalized))</w:t>"
    }

    private static func table(_ rows: [[String]], profile: OfficialDocumentProfile) -> String {
        let columnCount = rows.map(\.count).max() ?? 1
        let contentWidth = max(1, profile.contentWidthTwips)
        let columnWidth = max(1, contentWidth / columnCount)
        let grid = (0..<columnCount).map { _ in "<w:gridCol w:w=\"\(columnWidth)\"/>" }.joined()
        let body = rows.enumerated().map { rowIndex, row in
            let header = rowIndex == 0
            let headerProperty = header ? "<w:tblHeader w:val=\"true\"/>" : ""
            let trailingGrid = row.count < columnCount
                ? "<w:gridAfter w:val=\"\(columnCount - row.count)\"/>"
                : ""
            let rowProperties = header || row.count < columnCount
                ? "<w:trPr>\(headerProperty)\(trailingGrid)</w:trPr>"
                : ""
            let shade = header ? "<w:shd w:val=\"clear\" w:color=\"auto\" w:fill=\"F4F4F5\"/>" : ""
            let bold = header ? "<w:b/>" : ""
            let cells = row.map { cell in
                "<w:tc><w:tcPr><w:tcW w:w=\"\(columnWidth)\" w:type=\"dxa\"/>\(shade)<w:tcMar><w:top w:w=\"60\" w:type=\"dxa\"/><w:left w:w=\"80\" w:type=\"dxa\"/><w:bottom w:w=\"60\" w:type=\"dxa\"/><w:right w:w=\"80\" w:type=\"dxa\"/></w:tcMar></w:tcPr><w:p><w:pPr><w:pStyle w:val=\"Normal\"/></w:pPr><w:r><w:rPr>\(bold)<w:spacing w:val=\"\(profile.letterSpacingTwips)\"/><w:sz w:val=\"24\"/><w:szCs w:val=\"24\"/></w:rPr><w:t xml:space=\"preserve\">\(xml(cell))</w:t></w:r></w:p></w:tc>"
            }.joined()
            return "<w:tr>\(rowProperties)\(cells)</w:tr>"
        }.joined()
        return "<w:tbl><w:tblPr><w:tblStyle w:val=\"TableGrid\"/><w:tblW w:w=\"\(contentWidth)\" w:type=\"dxa\"/><w:tblLayout w:type=\"fixed\"/><w:tblLook w:val=\"04A0\" w:firstRow=\"1\" w:lastRow=\"0\" w:firstColumn=\"1\" w:lastColumn=\"0\" w:noHBand=\"0\" w:noVBand=\"1\"/></w:tblPr><w:tblGrid>\(grid)</w:tblGrid>\(body)</w:tbl>"
    }

    private static func halfPoints(_ pointSize: Int) -> Int { pointSize * 2 }

    private static func xml(_ value: String) -> String {
        guard value.unicodeScalars.contains(where: { $0 == "&" || $0 == "<" || $0 == ">" || $0 == "\"" || $0 == "'" }) else {
            return value
        }
        var escaped = ""
        escaped.reserveCapacity(value.count + 16)
        for scalar in value.unicodeScalars {
            switch scalar {
            case "&": escaped += "&amp;"
            case "<": escaped += "&lt;"
            case ">": escaped += "&gt;"
            case "\"": escaped += "&quot;"
            case "'": escaped += "&apos;"
            default: escaped.unicodeScalars.append(scalar)
            }
        }
        return escaped
    }
}
