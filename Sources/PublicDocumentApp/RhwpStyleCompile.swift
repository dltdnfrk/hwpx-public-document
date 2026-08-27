import Foundation

enum RhwpStyleCompile {
    static func apply(to hwpx: URL, work: URL) throws {
        let unpacked = work.appendingPathComponent("owpml", isDirectory: true)
        try FileManager.default.createDirectory(at: unpacked, withIntermediateDirectories: true)
        try run("/usr/bin/unzip", ["-o", "-q", hwpx.path, "-d", unpacked.path])
        let header = unpacked.appendingPathComponent("Contents/header.xml")
        let section = unpacked.appendingPathComponent("Contents/section0.xml")
        try patchHeader(at: header)
        try patchSection(at: section)
        try run("/usr/bin/zip", ["-q", "-u", hwpx.path, "Contents/header.xml", "Contents/section0.xml"], directory: unpacked)
    }

    private static func patchHeader(at url: URL) throws {
        var xml = try String(contentsOf: url, encoding: .utf8)
        xml = xml.replacingOccurrences(of: "fontCnt=\"1\"", with: "fontCnt=\"3\"")
        xml = xml.replacingOccurrences(
            of: "<hh:fontface lang=\"HANGUL\" fontCnt=\"3\"><hh:font id=\"0\" face=\"AppleMyungjo\" type=\"TTF\" isEmbedded=\"0\"/>",
            with: "<hh:fontface lang=\"HANGUL\" fontCnt=\"3\"><hh:font id=\"0\" face=\"휴먼명조\" type=\"TTF\" isEmbedded=\"0\"/><hh:font id=\"1\" face=\"헤드라인\" type=\"TTF\" isEmbedded=\"0\"/><hh:font id=\"2\" face=\"맑은고딕\" type=\"TTF\" isEmbedded=\"0\"/>"
        )
        let latinExtra = "<hh:font id=\"1\" face=\"Apple SD Gothic Neo\" type=\"TTF\" isEmbedded=\"0\"/><hh:font id=\"2\" face=\"Apple SD Gothic Neo\" type=\"TTF\" isEmbedded=\"0\"/>"
        for lang in ["LATIN", "HANJA", "JAPANESE", "OTHER", "SYMBOL", "USER"] {
            let needle = "<hh:fontface lang=\"\(lang)\" fontCnt=\"3\"><hh:font id=\"0\" face=\"AppleMyungjo\" type=\"TTF\" isEmbedded=\"0\"/>"
            xml = xml.replacingOccurrences(of: needle, with: needle + latinExtra)
        }
        xml = xml.replacingOccurrences(of: "<hh:charProperties itemCnt=\"1\">", with: "<hh:charProperties itemCnt=\"5\">")
        xml = xml.replacingOccurrences(
            of: "</hh:charPr></hh:charProperties>",
            with: "</hh:charPr>"
                + charPr(id: 1, height: 1600, font: 1, bold: true)
                + charPr(id: 2, height: 1600, font: 1, bold: true)
                + charPr(id: 3, height: 1500, font: 0, bold: false)
                + charPr(id: 4, height: 1200, font: 2, bold: false)
                + "</hh:charProperties>"
        )
        xml = xml.replacingOccurrences(of: "<hh:paraProperties itemCnt=\"2\">", with: "<hh:paraProperties itemCnt=\"3\">")
        if let range = xml.range(of: "</hh:paraPr></hh:paraProperties>") {
            xml.replaceSubrange(range, with: "</hh:paraPr>" + titleParaPr() + "</hh:paraProperties>")
        }
        xml = xml.replacingOccurrences(of: "<hh:styles itemCnt=\"1\">", with: "<hh:styles itemCnt=\"5\">")
        xml = xml.replacingOccurrences(
            of: "</hh:styles>",
            with: style(id: 1, name: "제목", eng: "Title", para: 2, char: 1)
                + style(id: 2, name: "소제목", eng: "Heading2", para: 0, char: 2)
                + style(id: 3, name: "본문", eng: "Normal", para: 0, char: 3)
                + style(id: 4, name: "참고", eng: "IntenseQuote", para: 0, char: 4)
                + "</hh:styles>"
        )
        try xml.write(to: url, atomically: true, encoding: .utf8)
    }

    private static func patchSection(at url: URL) throws {
        var xml = try String(contentsOf: url, encoding: .utf8)
        let regex = try NSRegularExpression(pattern: "<hp:p id=\"(\\d+)\" paraPrIDRef=\"0\" styleIDRef=\"0\"([^>]*)>([\\s\\S]*?)</hp:p>")
        let original = xml
        let matches = regex.matches(in: original, range: NSRange(original.startIndex..<original.endIndex, in: original))
        for match in matches.reversed() {
            guard let full = Range(match.range, in: original),
                  let bodyRange = Range(match.range(at: 3), in: original)
            else { continue }
            let body = String(original[bodyRange])
            guard let textRange = body.range(of: "<hp:t>"),
                  let textEnd = body.range(of: "</hp:t>")
            else { continue }
            let text = String(body[textRange.upperBound..<textEnd.lowerBound])
            let mapped = mapStyle(text)
            var rewritten = String(original[full])
            rewritten = rewritten.replacingOccurrences(
                of: "paraPrIDRef=\"0\" styleIDRef=\"0\"",
                with: "paraPrIDRef=\"\(mapped.para)\" styleIDRef=\"\(mapped.style)\""
            )
            rewritten = rewritten.replacingOccurrences(of: "charPrIDRef=\"0\"", with: "charPrIDRef=\"\(mapped.char)\"")
            xml.replaceSubrange(full, with: rewritten)
        }
        try xml.write(to: url, atomically: true, encoding: .utf8)
    }

    private static func mapStyle(_ text: String) -> (para: Int, style: Int, char: Int) {
        if text.hasPrefix("□ ") || text.hasPrefix("1. ") || text.hasPrefix("2. ") || text.hasPrefix("3. ")
            || text.hasPrefix("4. ") || text.hasPrefix("5. ") || text.hasPrefix("6. ") {
            return (0, 2, 2)
        }
        if text.hasPrefix("※") || text.hasPrefix("*") {
            return (0, 4, 4)
        }
        if text.hasPrefix("○") || text.hasPrefix("가. ") || text.hasPrefix("-") {
            return (0, 3, 3)
        }
        return (2, 1, 1)
    }

    private static func charPr(id: Int, height: Int, font: Int, bold: Bool) -> String {
        let refs = "hangul=\"\(font)\" latin=\"\(font)\" hanja=\"\(font)\" japanese=\"\(font)\" other=\"\(font)\" symbol=\"\(font)\" user=\"\(font)\""
        let hundred = "hangul=\"100\" latin=\"100\" hanja=\"100\" japanese=\"100\" other=\"100\" symbol=\"100\" user=\"100\""
        let zero = "hangul=\"0\" latin=\"0\" hanja=\"0\" japanese=\"0\" other=\"0\" symbol=\"0\" user=\"0\""
        return "<hh:charPr id=\"\(id)\" height=\"\(height)\" textColor=\"#000000\" shadeColor=\"none\" useFontSpace=\"0\" useKerning=\"0\" symMark=\"NONE\" borderFillIDRef=\"1\"><hh:fontRef \(refs)/>"
            + (bold ? "<hh:bold/>" : "")
            + "<hh:ratio \(hundred)/><hh:spacing \(zero)/><hh:relSz \(hundred)/><hh:offset \(zero)/><hh:underline type=\"NONE\" shape=\"SOLID\" color=\"#000000\"/><hh:strikeout shape=\"NONE\" color=\"#000000\"/><hh:outline type=\"NONE\"/><hh:shadow type=\"NONE\" color=\"#000000\" offsetX=\"0\" offsetY=\"0\"/></hh:charPr>"
    }

    private static func titleParaPr() -> String {
        "<hh:paraPr id=\"2\" tabPrIDRef=\"0\" condense=\"0\" fontLineHeight=\"0\" snapToGrid=\"1\" suppressLineNumbers=\"0\" checked=\"0\"><hh:align horizontal=\"CENTER\" vertical=\"CENTER\"/><hh:heading type=\"NONE\" id=\"0\" level=\"0\"/><hh:breakSetting breakLatinWord=\"KEEP_WORD\" breakNonLatinWord=\"KEEP_WORD\" widowOrphan=\"0\" keepWithNext=\"0\" keepLines=\"0\" pageBreakBefore=\"0\" lineWrap=\"BREAK\"/></hh:paraPr>"
    }

    private static func style(id: Int, name: String, eng: String, para: Int, char: Int) -> String {
        "<hh:style id=\"\(id)\" type=\"PARA\" name=\"\(name)\" engName=\"\(eng)\" paraPrIDRef=\"\(para)\" charPrIDRef=\"\(char)\" nextStyleIDRef=\"0\" langID=\"1042\" lockForm=\"0\"/>"
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
