import Foundation

enum OfficialLayoutProfileSelfTest {
    static func run(toolkit: URL, tokens: URL, output: URL) throws -> [String: Any] {
        let profile = try OfficialDocumentProfile.load(toolkitURL: toolkit, tokenURL: tokens)
        let presets = profile.presets.values
            .sorted { $0.styleID < $1.styleID }
            .map {
                [
                    "styleID": $0.styleID,
                    "docxStyleId": $0.docxStyleId,
                    "hangulFont": $0.hangulFont,
                    "wordFont": $0.wordFont,
                    "pointSize": $0.pointSize,
                    "bold": $0.bold,
                    "align": $0.align,
                ] as [String: Any]
            }
        let probeText = "1. 배경 ○ 첫 항목. ○ 둘째 함. 1. 표준지침 2. 교육 - 세부 하나 - 세부 둘"
        let receipt: [String: Any] = [
            "schemaVersion": 1,
            "sourceFingerprint": profile.sourceFingerprint,
            "page": [
                "widthTwips": profile.page.widthTwips,
                "heightTwips": profile.page.heightTwips,
                "top": profile.page.top,
                "right": profile.page.right,
                "bottom": profile.page.bottom,
                "left": profile.page.left,
            ],
            "hwpxMargins": [
                "top": profile.hwpxTop,
                "right": profile.hwpxRight,
                "bottom": profile.hwpxBottom,
                "left": profile.hwpxLeft,
            ],
            "letterSpacingHwp": profile.letterSpacingHwp,
            "letterSpacingTwips": profile.letterSpacingTwips,
            "presets": presets,
            "typesetProbe": [
                "source": probeText,
                "lines": OfficialTypeset.lines(probeText),
            ],
        ]
        let data = try JSONSerialization.data(
            withJSONObject: receipt,
            options: [.prettyPrinted, .sortedKeys]
        )
        try data.write(to: output, options: .atomic)
        return receipt
    }
}
