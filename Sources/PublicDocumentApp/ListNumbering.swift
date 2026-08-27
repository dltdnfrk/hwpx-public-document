import Foundation

enum ListNumbering {
    static let statutory = ["1. ", "가. ", "1) ", "가) ", "(1) ", "(가) ", "① ", "㉮ "]
    static let guidebook = ["□ ", "○", "-", "※", "*"]

    static func isDraft(_ templateID: String) -> Bool {
        templateID == "public-draft"
    }

    static func headingPrefix(templateID: String, index: Int) -> String {
        isDraft(templateID) ? "\(index + 1). " : "□ "
    }

    static func bodyPrefix(templateID: String) -> String {
        isDraft(templateID) ? "가. " : "○ "
    }

    static func markers(templateID: String) -> [String] {
        isDraft(templateID) ? statutory : guidebook
    }
}
