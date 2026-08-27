import Foundation

enum StatuteCitations {
    static let pattern = try! NSRegularExpression(
        pattern: "행정업무의 운영 및 혁신에 관한 규정(?: 시행규칙)? 제\\d+조[①②③④⑤⑥⑦⑧⑨⑩]?|공공문서 작성 지침 제\\d+조|편람 제\\d+조|제\\d+조[①②③④⑤⑥⑦⑧⑨⑩]?"
    )

    static func review(_ values: [String]) -> [[String: String]] {
        let verified = Set(loadVerified())
        var seen: [String: [String: String]] = [:]
        for value in values {
            let range = NSRange(value.startIndex..<value.endIndex, in: value)
            pattern.enumerateMatches(in: value, range: range) { match, _, _ in
                guard let match, let inner = Range(match.range, in: value) else { return }
                let citation = String(value[inner])
                let confirmed = verified.contains(citation)
                seen[citation] = [
                    "citation": citation,
                    "verified": confirmed ? "true" : "false",
                    "label": confirmed ? "확인됨" : "법령 인용 미확인",
                ]
            }
        }
        return Array(seen.values)
    }

    private static func loadVerified() -> [String] {
        let bundled = Bundle.main.resourceURL?.appendingPathComponent("Rules/verified-statute-citations-1.0.0.json")
        let source = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
            .appendingPathComponent("Resources/Rules/verified-statute-citations-1.0.0.json")
        for candidate in [bundled, source].compactMap({ $0 }) {
            guard let data = try? Data(contentsOf: candidate),
                  let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let verified = object["verified"] as? [String]
            else { continue }
            return verified
        }
        return []
    }
}
