import Foundation

struct RhwpLargeTextReplacement {
    let marker: String
    let text: String
}

enum RhwpLargeTextCompile {
    static func apply(
        to hwpx: URL,
        replacements: [RhwpLargeTextReplacement],
        work: URL
    ) throws {
        guard !replacements.isEmpty else { return }
        let unpacked = work.appendingPathComponent("owpml-large-text", isDirectory: true)
        try FileManager.default.createDirectory(at: unpacked, withIntermediateDirectories: true)
        try run("/usr/bin/unzip", ["-o", "-q", hwpx.path, "-d", unpacked.path])
        let section = unpacked.appendingPathComponent("Contents/section0.xml")
        let original = try String(contentsOf: section, encoding: .utf8)
        let byMarker = Dictionary(uniqueKeysWithValues: replacements.map {
            ($0.marker, $0.text)
        })
        let expression = try NSRegularExpression(
            pattern: #"<hp:t>(__PUBLIC_DOCUMENT_LARGE_TEXT_\d{6}__)</hp:t>"#
        )
        let matches = expression.matches(
            in: original,
            range: NSRange(original.startIndex..<original.endIndex, in: original)
        )
        guard matches.count == replacements.count else {
            throw ExportError.rhwpFailed("대용량 문단 표식 수가 OWPML과 다릅니다")
        }
        var seen: Set<String> = []
        var xml = ""
        xml.reserveCapacity(
            original.utf8.count + replacements.reduce(0) { $0 + $1.text.utf8.count }
        )
        var cursor = original.startIndex
        for match in matches {
            guard let full = Range(match.range, in: original),
                  let markerRange = Range(match.range(at: 1), in: original)
            else {
                throw ExportError.rhwpFailed("대용량 문단 표식 범위가 올바르지 않습니다")
            }
            let marker = String(original[markerRange])
            guard let text = byMarker[marker], seen.insert(marker).inserted else {
                throw ExportError.rhwpFailed("대용량 문단 표식이 없거나 중복되었습니다")
            }
            xml.append(contentsOf: original[cursor..<full.lowerBound])
            xml.append("<hp:t>")
            xml.append(xmlEscape(text))
            xml.append("</hp:t>")
            cursor = full.upperBound
        }
        xml.append(contentsOf: original[cursor...])
        try xml.write(to: section, atomically: true, encoding: .utf8)
        try run("/usr/bin/zip", ["-q", "-d", hwpx.path, "Contents/section0.xml"])
        try run(
            "/usr/bin/zip",
            ["-q", hwpx.path, "Contents/section0.xml"],
            directory: unpacked
        )
    }

    private static func xmlEscape(_ value: String) -> String {
        value
            .replacingOccurrences(of: "&", with: "&amp;")
            .replacingOccurrences(of: "<", with: "&lt;")
            .replacingOccurrences(of: ">", with: "&gt;")
    }

    private static func run(
        _ launch: String,
        _ arguments: [String],
        directory: URL? = nil
    ) throws {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: launch)
        process.arguments = arguments
        process.currentDirectoryURL = directory
        process.standardOutput = Pipe()
        process.standardError = Pipe()
        try process.run()
        process.waitUntilExit()
        guard process.terminationStatus == 0 else {
            throw ExportError.rhwpFailed("OWPML 대용량 문단 컴파일 실패: \(launch)")
        }
    }
}
