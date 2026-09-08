import Foundation

enum RhwpStyleCompile {
    static func apply(
        to hwpx: URL,
        work: URL,
        profile: OfficialDocumentProfile,
        project: DocumentProject
    ) throws {
        if !project.elements.isEmpty,
           project.elements.allSatisfy({ $0.styleID == "performance-body" }) {
            return
        }
        let unpacked = work.appendingPathComponent("owpml", isDirectory: true)
        try FileManager.default.createDirectory(at: unpacked, withIntermediateDirectories: true)
        try run("/usr/bin/unzip", ["-o", "-q", hwpx.path, "-d", unpacked.path])
        let header = unpacked.appendingPathComponent("Contents/header.xml")
        let section = unpacked.appendingPathComponent("Contents/section0.xml")
        try patchHeader(at: header, profile: profile)
        try patchSection(at: section, profile: profile, project: project)
        try run(
            "/usr/bin/zip",
            ["-q", "-d", hwpx.path, "Contents/header.xml", "Contents/section0.xml"]
        )
        try run(
            "/usr/bin/zip",
            ["-q", hwpx.path, "Contents/header.xml", "Contents/section0.xml"],
            directory: unpacked
        )
    }

    private static func patchHeader(at url: URL, profile: OfficialDocumentProfile) throws {
        guard let title = profile.presets["style-title"],
              let heading = profile.presets["style-section-heading"],
              let body = profile.presets["style-body"],
              let reference = profile.presets["style-reference-note"]
        else {
            throw ExportError.invalidPackage("official layout profile is missing HWPX presets")
        }
        var xml = try String(contentsOf: url, encoding: .utf8)
        xml = xml.replacingOccurrences(of: "fontCnt=\"1\"", with: "fontCnt=\"3\"")
        xml = xml.replacingOccurrences(
            of: "<hh:fontface lang=\"HANGUL\" fontCnt=\"3\"><hh:font id=\"0\" face=\"AppleMyungjo\" type=\"TTF\" isEmbedded=\"0\"/>",
            with: "<hh:fontface lang=\"HANGUL\" fontCnt=\"3\"><hh:font id=\"0\" face=\"\(xmlAttribute(body.hangulFont))\" type=\"TTF\" isEmbedded=\"0\"/><hh:font id=\"1\" face=\"\(xmlAttribute(title.hangulFont))\" type=\"TTF\" isEmbedded=\"0\"/><hh:font id=\"2\" face=\"\(xmlAttribute(reference.hangulFont))\" type=\"TTF\" isEmbedded=\"0\"/>"
        )
        let latinExtra = "<hh:font id=\"1\" face=\"\(xmlAttribute(title.wordFont))\" type=\"TTF\" isEmbedded=\"0\"/><hh:font id=\"2\" face=\"\(xmlAttribute(reference.wordFont))\" type=\"TTF\" isEmbedded=\"0\"/>"
        for lang in ["LATIN", "HANJA", "JAPANESE", "OTHER", "SYMBOL", "USER"] {
            let needle = "<hh:fontface lang=\"\(lang)\" fontCnt=\"3\"><hh:font id=\"0\" face=\"AppleMyungjo\" type=\"TTF\" isEmbedded=\"0\"/>"
            xml = xml.replacingOccurrences(of: needle, with: needle + latinExtra)
        }
        xml = xml.replacingOccurrences(of: "<hh:charProperties itemCnt=\"1\">", with: "<hh:charProperties itemCnt=\"5\">")
        xml = xml.replacingOccurrences(
            of: "</hh:charPr></hh:charProperties>",
            with: "</hh:charPr>"
                + charPr(id: 1, height: title.pointSize * 100, font: 1, bold: title.bold)
                + charPr(id: 2, height: heading.pointSize * 100, font: 1, bold: heading.bold)
                + charPr(id: 3, height: body.pointSize * 100, font: 0, bold: body.bold, spacing: profile.letterSpacingHwp)
                + charPr(id: 4, height: reference.pointSize * 100, font: 2, bold: reference.bold)
                + "</hh:charProperties>"
        )
        xml = xml.replacingOccurrences(of: "<hh:paraProperties itemCnt=\"2\">", with: "<hh:paraProperties itemCnt=\"11\">")
        if let range = xml.range(of: "</hh:paraPr></hh:paraProperties>") {
            let hierarchy = [
                (3, 2100, 2100),
                (4, 3600, 1800),
                (5, 5400, 1800),
                (6, 7200, 1800),
                (7, 9000, 1800),
                (8, 10800, 1800),
                (9, 12600, 1800),
                (10, 14400, 1800),
            ].map { hangingParaPr(id: $0.0, left: $0.1, hanging: $0.2) }.joined()
            xml.replaceSubrange(
                range,
                with: "</hh:paraPr>"
                    + titleParaPr(align: title.align)
                    + hierarchy
                    + "</hh:paraProperties>"
            )
        }
        xml = xml.replacingOccurrences(of: "<hh:styles itemCnt=\"1\">", with: "<hh:styles itemCnt=\"5\">")
        xml = xml.replacingOccurrences(
            of: "</hh:styles>",
            with: style(id: 1, name: "제목", eng: title.docxStyleId, para: 2, char: 1)
                + style(id: 2, name: "소제목", eng: heading.docxStyleId, para: 0, char: 2)
                + style(id: 3, name: "본문", eng: body.docxStyleId, para: 0, char: 3)
                + style(id: 4, name: "참고", eng: reference.docxStyleId, para: 0, char: 4)
                + "</hh:styles>"
        )
        try xml.write(to: url, atomically: true, encoding: .utf8)
    }

    private static func patchSection(
        at url: URL,
        profile: OfficialDocumentProfile,
        project: DocumentProject
    ) throws {
        var xml = try String(contentsOf: url, encoding: .utf8)
        xml = patchPageMargin(xml, profile: profile)
        let regex = try NSRegularExpression(pattern: "<hp:p id=\"(\\d+)\" paraPrIDRef=\"0\" styleIDRef=\"0\"([^>]*)>([\\s\\S]*?)</hp:p>")
        let original = xml
        let matches = regex.matches(in: original, range: NSRange(original.startIndex..<original.endIndex, in: original))
        let elements = project.elements.sorted { $0.order < $1.order }
        let elementsByText = Dictionary(grouping: elements) { xmlEscape($0.text) }
        var textOffsets: [String: Int] = [:]
        let sourceElements = matches.map { match -> DocumentElement? in
            guard let bodyRange = Range(match.range(at: 3), in: original) else {
                return nil
            }
            let body = String(original[bodyRange])
            guard let textRange = body.range(of: "<hp:t>"),
                  let textEnd = body.range(of: "</hp:t>")
            else { return nil }
            let text = String(body[textRange.upperBound..<textEnd.lowerBound])
            let offset = textOffsets[text, default: 0]
            textOffsets[text] = offset + 1
            return elementsByText[text].flatMap {
                offset < $0.count ? $0[offset] : nil
            }
        }
        for (elementIndex, match) in matches.enumerated().reversed() {
            guard let full = Range(match.range, in: original),
                  let idRange = Range(match.range(at: 1), in: original),
                  let bodyRange = Range(match.range(at: 3), in: original)
            else { continue }
            let body = String(original[bodyRange])
            if body.contains("<hp:tbl") { continue }
            guard let textRange = body.range(of: "<hp:t>"),
                  let textEnd = body.range(of: "</hp:t>")
            else { continue }
            let text = String(body[textRange.upperBound..<textEnd.lowerBound])
            let id = Int(original[idRange]) ?? 0
            let lines = OfficialTypeset.lines(text)
            let sourceElement = sourceElements[elementIndex]
            let isTitle = sourceElement?.styleID == "style-title"
            let sourceStyleID = sourceElement?.styleID
            let pieces = (lines.isEmpty ? [text] : lines).enumerated().map { index, line in
                rewriteParagraph(
                    String(original[full]),
                    originalID: id,
                    index: index,
                    originalText: text,
                    line: line,
                    isTitle: isTitle,
                    sourceStyleID: sourceStyleID
                )
            }
            xml.replaceSubrange(full, with: pieces.joined())
        }
        try xml.write(to: url, atomically: true, encoding: .utf8)
    }

    private static func rewriteParagraph(
        _ source: String,
        originalID: Int,
        index: Int,
        originalText: String,
        line: String,
        isTitle: Bool,
        sourceStyleID: String?
    ) -> String {
        let mapped = mapStyle(line, isTitle: isTitle, sourceStyleID: sourceStyleID)
        var rewritten = source
        rewritten = rewritten.replacingOccurrences(
            of: "paraPrIDRef=\"0\" styleIDRef=\"0\"",
            with: "paraPrIDRef=\"\(mapped.para)\" styleIDRef=\"\(mapped.style)\""
        )
        rewritten = rewritten.replacingOccurrences(of: "charPrIDRef=\"0\"", with: "charPrIDRef=\"\(mapped.char)\"")
        rewritten = rewritten.replacingOccurrences(
            of: "<hp:p id=\"\(originalID)\"",
            with: "<hp:p id=\"\(originalID * 1000 + index)\""
        )
        rewritten = rewritten.replacingOccurrences(of: "<hp:t>\(originalText)</hp:t>", with: "<hp:t>\(line)</hp:t>")
        return rewritten
    }

    private static func patchPageMargin(_ xml: String, profile: OfficialDocumentProfile) -> String {
        guard let regex = try? NSRegularExpression(
            pattern: #"hp:margin header="[^"]*" footer="[^"]*" gutter="[^"]*" left="[^"]*" right="[^"]*" top="[^"]*" bottom="[^"]*""#
        ) else { return xml }
        return regex.stringByReplacingMatches(
            in: xml,
            range: NSRange(xml.startIndex..., in: xml),
            withTemplate: "hp:margin header=\"4252\" footer=\"4252\" gutter=\"0\" left=\"\(profile.hwpxLeft)\" right=\"\(profile.hwpxRight)\" top=\"\(profile.hwpxTop)\" bottom=\"\(profile.hwpxBottom)\""
        )
    }

    private static func mapStyle(
        _ text: String,
        isTitle: Bool,
        sourceStyleID: String?
    ) -> (para: Int, style: Int, char: Int) {
        if isTitle { return (2, 1, 1) }
        if sourceStyleID == "performance-body" { return (2, 1, 1) }
        if let hang = OfficialTypeset.hanging(text) {
            let para: Int
            switch (hang.left, hang.hanging) {
            case (420, 420): para = 3
            case (720, 360): para = 4
            case (1080, 360): para = 5
            case (1440, 360): para = 6
            case (1800, 360): para = 7
            case (2160, 360): para = 8
            case (2520, 360): para = 9
            case (2880, 360): para = 10
            default: para = 0
            }
            if text.hasPrefix("□ ") { return (para, 2, 2) }
            if text.hasPrefix("※") || text.hasPrefix("*") { return (para, 4, 4) }
            return (para, 3, 3)
        }
        return (0, 3, 3)
    }

    private static func charPr(id: Int, height: Int, font: Int, bold: Bool, spacing: Int = 0) -> String {
        let refs = "hangul=\"\(font)\" latin=\"\(font)\" hanja=\"\(font)\" japanese=\"\(font)\" other=\"\(font)\" symbol=\"\(font)\" user=\"\(font)\""
        let hundred = "hangul=\"100\" latin=\"100\" hanja=\"100\" japanese=\"100\" other=\"100\" symbol=\"100\" user=\"100\""
        let space = "hangul=\"\(spacing)\" latin=\"\(spacing)\" hanja=\"\(spacing)\" japanese=\"\(spacing)\" other=\"\(spacing)\" symbol=\"\(spacing)\" user=\"\(spacing)\""
        let zero = "hangul=\"0\" latin=\"0\" hanja=\"0\" japanese=\"0\" other=\"0\" symbol=\"0\" user=\"0\""
        return "<hh:charPr id=\"\(id)\" height=\"\(height)\" textColor=\"#000000\" shadeColor=\"none\" useFontSpace=\"0\" useKerning=\"0\" symMark=\"NONE\" borderFillIDRef=\"1\"><hh:fontRef \(refs)/>"
            + (bold ? "<hh:bold/>" : "")
            + "<hh:ratio \(hundred)/><hh:spacing \(space)/><hh:relSz \(hundred)/><hh:offset \(zero)/><hh:underline type=\"NONE\" shape=\"SOLID\" color=\"#000000\"/><hh:strikeout shape=\"NONE\" color=\"#000000\"/><hh:outline type=\"NONE\"/><hh:shadow type=\"NONE\" color=\"#000000\" offsetX=\"0\" offsetY=\"0\"/></hh:charPr>"
    }

    private static func titleParaPr(align: String) -> String {
        let horizontal = align == "center" ? "CENTER" : "LEFT"
        return "<hh:paraPr id=\"2\" tabPrIDRef=\"0\" condense=\"0\" fontLineHeight=\"0\" snapToGrid=\"1\" suppressLineNumbers=\"0\" checked=\"0\"><hh:align horizontal=\"\(horizontal)\" vertical=\"CENTER\"/><hh:heading type=\"NONE\" id=\"0\" level=\"0\"/><hh:breakSetting breakLatinWord=\"KEEP_WORD\" breakNonLatinWord=\"KEEP_WORD\" widowOrphan=\"0\" keepWithNext=\"0\" keepLines=\"0\" pageBreakBefore=\"0\" lineWrap=\"BREAK\"/></hh:paraPr>"
    }

    private static func hangingParaPr(id: Int, left: Int, hanging: Int) -> String {
        "<hh:paraPr id=\"\(id)\" tabPrIDRef=\"0\" condense=\"0\" fontLineHeight=\"0\" snapToGrid=\"1\" suppressLineNumbers=\"0\" checked=\"0\"><hh:align horizontal=\"JUSTIFY\" vertical=\"BASELINE\"/><hh:heading type=\"NONE\" id=\"0\" level=\"0\"/><hh:breakSetting breakLatinWord=\"KEEP_WORD\" breakNonLatinWord=\"KEEP_WORD\" widowOrphan=\"0\" keepWithNext=\"0\" keepLines=\"0\" pageBreakBefore=\"0\" lineWrap=\"BREAK\"/><hh:margin intent=\"\(-hanging)\" left=\"\(left)\" right=\"0\" prev=\"0\" next=\"0\"/></hh:paraPr>"
    }

    private static func style(id: Int, name: String, eng: String, para: Int, char: Int) -> String {
        "<hh:style id=\"\(id)\" type=\"PARA\" name=\"\(xmlAttribute(name))\" engName=\"\(xmlAttribute(eng))\" paraPrIDRef=\"\(para)\" charPrIDRef=\"\(char)\" nextStyleIDRef=\"0\" langID=\"1042\" lockForm=\"0\"/>"
    }

    private static func xmlAttribute(_ value: String) -> String {
        value
            .replacingOccurrences(of: "&", with: "&amp;")
            .replacingOccurrences(of: "<", with: "&lt;")
            .replacingOccurrences(of: ">", with: "&gt;")
            .replacingOccurrences(of: "\"", with: "&quot;")
            .replacingOccurrences(of: "'", with: "&apos;")
    }

    private static func xmlEscape(_ value: String) -> String {
        value
            .replacingOccurrences(of: "&", with: "&amp;")
            .replacingOccurrences(of: "<", with: "&lt;")
            .replacingOccurrences(of: ">", with: "&gt;")
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
            throw ExportError.rhwpFailed("OWPML style compile failed: \(launch)")
        }
    }
}
