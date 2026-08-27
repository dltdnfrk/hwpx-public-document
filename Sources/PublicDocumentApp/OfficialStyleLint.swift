import Foundation

struct OfficialStyleLintFinding: Codable, Equatable {
    let ruleID: String
    let citation: String
    let message: String
    let dryRun: Bool
}

struct OfficialStyleLintReport: Codable, Equatable {
    let dryRun: Bool
    let findings: [OfficialStyleLintFinding]
}

enum OfficialStyleLint {
    private struct FilePayload: Decodable {
        struct Rule: Decodable {
            let id: String
            let kind: String
            let citation: String
            let message: String
        }
        let rules: [Rule]
    }

    static func dryRun(project: DocumentProject, catalog: TemplateCatalogPayload?) -> OfficialStyleLintReport {
        let rules = (try? loadRules()) ?? []
        let applied = catalog.flatMap { payload in
            payload.entries.first { $0.templateID == project.templateBinding.templateID }?.officialRules
        } ?? []
        let fields = Set(applied.map(\.field))
        let titleRule = applied.filter { $0.field == .title }.max { $0.precedence < $1.precedence }
        var findings: [OfficialStyleLintFinding] = []
        for rule in rules {
            let hit: Bool
            switch rule.kind {
            case "endMark":
                hit = fields.contains(.endMark) && !OfficialRuleSkeleton.hasEndMark(project.elements)
            case "attachment":
                hit = fields.contains(.attachment)
                    && OfficialRuleSkeleton.hasAttachments(project)
                    && !OfficialRuleSkeleton.hasAttachmentLabel(project.elements)
            case "senderName":
                hit = fields.contains(.senderName)
                    && !OfficialRuleSkeleton.isInternalApproval(project.elements)
                    && !OfficialRuleSkeleton.hasSenderName(project.elements)
            case "titleLock":
                hit = fields.contains(.title) && titleRule.map { project.title != $0.requiredValue } ?? false
            default:
                hit = false
            }
            if hit {
                findings.append(OfficialStyleLintFinding(
                    ruleID: rule.id,
                    citation: rule.citation,
                    message: rule.message,
                    dryRun: true
                ))
            }
        }
        return OfficialStyleLintReport(dryRun: true, findings: findings)
    }

    private static func loadRules() throws -> [FilePayload.Rule] {
        let bundled = Bundle.main.resourceURL?.appendingPathComponent("Rules/official-style-lint-1.0.0.json")
        let source = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
            .appendingPathComponent("Resources/Rules/official-style-lint-1.0.0.json")
        for candidate in [bundled, source].compactMap({ $0 }) where FileManager.default.fileExists(atPath: candidate.path) {
            return try JSONDecoder().decode(FilePayload.self, from: Data(contentsOf: candidate)).rules
        }
        return []
    }
}
