import Foundation

/// Compiles official-document tokens into line breaks and hanging indents.
/// Sources: 행정업무운영 편람 / 시행규칙 별표 4, 범피스1100 toolkit,
/// imsebeom/hwpx official-doc-style, airmang/hwpx-plugins official-document-rules,
/// commetee12-source/gov-report-docx 개조식 계층. Not an HWPX engine replacement.
enum OfficialTypeset {
    private static let attachmentTails = ["붙임", "별첨", "관련", "첨부"]
    private static let step: Int = 360

    static func lines(_ text: String) -> [String] {
        let source = text
            .replacingOccurrences(of: "\r\n", with: "\n")
            .replacingOccurrences(of: "\r", with: "\n")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard !source.isEmpty else { return [] }
        if source.utf8.count >= 1024 * 1024 {
            return [collapsed(source)]
        }
        let pattern = #"(?=\s*(?:○|□|※)\s)|(?=\s+-\s)|(?=\s+\d+단계:)|(?<=(?:함|음|다)\.\s)(?=\d+\.\s)|(?<=\s)(?=[1-9]\d?\.\s[가-힣○□])|(?<=\s)(?=[가나다라마바사아자차카타파하]\.\s[가-힣○□0-9])"#
        guard let regex = try? NSRegularExpression(pattern: pattern) else {
            return [collapsed(source)]
        }
        let full = NSRange(source.startIndex..., in: source)
        var parts: [String] = []
        var cursor = source.startIndex
        for match in regex.matches(in: source, range: full) {
            guard let at = Range(match.range, in: source) else { continue }
            if at.lowerBound > cursor {
                let piece = collapsed(String(source[cursor..<at.lowerBound]))
                if !piece.isEmpty { parts.append(piece) }
            }
            cursor = at.lowerBound
        }
        let tail = collapsed(String(source[cursor...]))
        if !tail.isEmpty { parts.append(tail) }
        let split = parts.isEmpty ? [collapsed(source)] : parts
        return mergeAttachmentNumbers(split)
    }

    /// Hanging indent in twips. 2타 ≈ 360. First-line offset is `left - hanging`.
    /// `1.` starts on the left baseline; `가.` and `-` step one 2타 each.
    static func hanging(_ line: String) -> (left: Int, hanging: Int)? {
        if line.hasPrefix("- ") { return (step * 2, step) }
        if line.hasPrefix("○") || line.hasPrefix("□") || line.hasPrefix("※") {
            return (420, 420)
        }
        if line.range(of: #"^\d+단계:"#, options: .regularExpression) != nil {
            return (420, 420)
        }
        if line.range(of: #"^제언\s+\d+\."#, options: .regularExpression) != nil {
            return (420, 420)
        }
        if line.range(of: #"^\d+\.\s"#, options: .regularExpression) != nil {
            return (420, 420)
        }
        if line.range(of: #"^[가나다라마바사아자차카타파하]\.\s"#, options: .regularExpression) != nil {
            return (step * 2, step)
        }
        if line.range(of: #"^\d+\)\s"#, options: .regularExpression) != nil {
            return (step * 3, step)
        }
        if line.range(of: #"^[가나다라마바사아자차카타파하]\)\s"#, options: .regularExpression) != nil {
            return (step * 4, step)
        }
        if line.range(of: #"^\(\d+\)\s"#, options: .regularExpression) != nil {
            return (step * 5, step)
        }
        if line.range(of: #"^\([가나다라마바사아자차카타파하]\)\s"#, options: .regularExpression) != nil {
            return (step * 6, step)
        }
        if line.range(of: #"^[①-⑳]\s"#, options: .regularExpression) != nil {
            return (step * 7, step)
        }
        if line.range(of: #"^[㉮-㉻]\s"#, options: .regularExpression) != nil {
            return (step * 8, step)
        }
        return nil
    }

    static func paragraphStyle(for line: String, fallback: String) -> String {
        if line.hasPrefix("※") || line.hasPrefix("*") { return "IntenseQuote" }
        return fallback
    }

    private static func mergeAttachmentNumbers(_ parts: [String]) -> [String] {
        var merged: [String] = []
        for part in parts {
            if let last = merged.last,
               attachmentTails.contains(where: { last == $0 || last.hasSuffix($0) }),
               part.range(of: #"^\d+\.\s"#, options: .regularExpression) != nil {
                merged[merged.count - 1] = last + " " + part
            } else {
                merged.append(part)
            }
        }
        return merged
    }

    private static func collapsed(_ value: String) -> String {
        value.split(whereSeparator: \.isWhitespace).joined(separator: " ")
    }
}
