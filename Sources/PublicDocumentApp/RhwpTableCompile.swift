import Foundation

enum RhwpTableCompile {
    static func apply(to hwpx: URL, project: DocumentProject, work: URL) throws {
        let tables = project.elements
            .sorted { $0.order == $1.order ? $0.elementID < $1.elementID : $0.order < $1.order }
            .filter { ["table", "approval-grid"].contains($0.kind) && !$0.contentHTML.isEmpty }
        guard !tables.isEmpty else { return }
        let unpacked = work.appendingPathComponent("owpml-tables", isDirectory: true)
        try FileManager.default.createDirectory(at: unpacked, withIntermediateDirectories: true)
        try run("/usr/bin/unzip", ["-o", "-q", hwpx.path, "-d", unpacked.path])
        let section = unpacked.appendingPathComponent("Contents/section0.xml")
        var xml = try String(contentsOf: section, encoding: .utf8)
        for (index, element) in tables.enumerated() {
            let rows = try ExportSerializers.tableRows(element)
            xml = try replaceRun(in: xml, text: element.text, with: tableRun(id: index, rows: rows), elementID: element.elementID)
        }
        try xml.write(to: section, atomically: true, encoding: .utf8)
        try run("/usr/bin/zip", ["-q", "-u", hwpx.path, "Contents/section0.xml"], directory: unpacked)
    }

    private static func replaceRun(in xml: String, text: String, with run: String, elementID: String) throws -> String {
        let escaped = xmlEscape(text)
        let pattern = "<hp:run charPrIDRef=\"\\d+\">\\s*<hp:t>\(NSRegularExpression.escapedPattern(for: escaped))</hp:t>\\s*</hp:run>"
        let regex = try NSRegularExpression(pattern: pattern)
        let range = NSRange(xml.startIndex..<xml.endIndex, in: xml)
        guard let match = regex.firstMatch(in: xml, range: range), let full = Range(match.range, in: xml) else {
            throw ExportError.rhwpFailed("\(elementID) 표 문단을 OWPML에서 찾지 못했습니다")
        }
        var next = xml
        next.replaceSubrange(full, with: run)
        return next
    }

    private static func tableRun(id: Int, rows: [[String]]) -> String {
        let columnCount = max(rows.map(\.count).max() ?? 1, 1)
        let padded = rows.map { row in
            row + Array(repeating: "", count: max(0, columnCount - row.count))
        }
        let width = 42520
        let cellWidth = width / columnCount
        let cellHeight = 2000
        let height = cellHeight * padded.count
        let body = padded.enumerated().map { rowIndex, row in
            let cells = row.enumerated().map { colIndex, value in
                cellXML(row: rowIndex, col: colIndex, width: cellWidth, height: cellHeight, text: value)
            }.joined()
            return "<hp:tr>\(cells)</hp:tr>"
        }.joined()
        return "<hp:run charPrIDRef=\"0\"><hp:tbl id=\"\(id)\" zOrder=\"0\" numberingType=\"TABLE\" textWrap=\"TOP_AND_BOTTOM\" textFlow=\"BOTH_SIDES\" lock=\"0\" dropcapstyle=\"None\" pageBreak=\"NONE\" repeatHeader=\"1\" rowCnt=\"\(padded.count)\" colCnt=\"\(columnCount)\" cellSpacing=\"0\" borderFillIDRef=\"2\" noAdjust=\"0\"><hp:sz width=\"\(width)\" widthRelTo=\"ABSOLUTE\" height=\"\(height)\" heightRelTo=\"ABSOLUTE\" protect=\"0\"/><hp:pos treatAsChar=\"1\" affectLSpacing=\"0\" flowWithText=\"1\" allowOverlap=\"0\" holdAnchorAndSO=\"0\" vertRelTo=\"PARA\" horzRelTo=\"PARA\" vertAlign=\"TOP\" horzAlign=\"LEFT\" vertOffset=\"0\" horzOffset=\"0\"/><hp:outMargin left=\"141\" right=\"141\" top=\"141\" bottom=\"141\"/><hp:inMargin left=\"510\" right=\"510\" top=\"141\" bottom=\"141\"/>\(body)</hp:tbl></hp:run>"
    }

    private static func cellXML(row: Int, col: Int, width: Int, height: Int, text: String) -> String {
        "<hp:tc header=\"\(row == 0 ? 1 : 0)\" hasMargin=\"0\" protect=\"0\" editable=\"0\" dirty=\"0\" borderFillIDRef=\"2\"><hp:subList id=\"\" textDirection=\"HORIZONTAL\" lineWrap=\"BREAK\" vertAlign=\"CENTER\" linkListIDRef=\"0\" linkListNextIDRef=\"0\" textWidth=\"0\" textHeight=\"0\" hasTextRef=\"0\" hasNumRef=\"0\"><hp:p id=\"0\" paraPrIDRef=\"0\" styleIDRef=\"0\" pageBreak=\"0\" columnBreak=\"0\" merged=\"0\"><hp:run charPrIDRef=\"0\"><hp:t>\(xmlEscape(text))</hp:t></hp:run></hp:p></hp:subList><hp:cellAddr colAddr=\"\(col)\" rowAddr=\"\(row)\"/><hp:cellSpan colSpan=\"1\" rowSpan=\"1\"/><hp:cellSz width=\"\(width)\" height=\"\(height)\"/><hp:cellMargin left=\"510\" right=\"510\" top=\"141\" bottom=\"141\"/></hp:tc>"
    }

    private static func xmlEscape(_ value: String) -> String {
        value
            .replacingOccurrences(of: "&", with: "&amp;")
            .replacingOccurrences(of: "<", with: "&lt;")
            .replacingOccurrences(of: ">", with: "&gt;")
            .replacingOccurrences(of: "\"", with: "&quot;")
            .replacingOccurrences(of: "'", with: "&apos;")
    }

    private static func run(_ launch: String, _ arguments: [String], directory: URL? = nil) throws {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: launch)
        process.arguments = arguments
        process.currentDirectoryURL = directory
        process.standardOutput = Pipe()
        process.standardError = Pipe()
        try process.run()
        process.waitUntilExit()
        guard process.terminationStatus == 0 else {
            throw ExportError.rhwpFailed("OWPML table compile failed: \(launch)")
        }
    }
}
