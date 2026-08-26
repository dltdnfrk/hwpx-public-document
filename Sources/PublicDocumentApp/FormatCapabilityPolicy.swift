import Foundation

enum FormatCapabilityPolicy {
    private static let structuralOnlyCapabilities: Set<String> = ["table-row", "table-cell"]
    private static let frozenCombinations = [
        "paragraph+strong+emphasis+underline",
        "paragraph+keep-together",
        "unordered-list+list-item+strong",
        "table+table-row+table-cell+strong",
        "approval-grid+table-row+table-cell",
        "review-marker+strong",
    ]

    static func lossReports(
        project: DocumentProject,
        format: DocumentFormat
    ) throws -> [LossReport] {
        try lossReports(
            observations: observedCapabilities(project: project),
            format: format
        )
    }

    static func lossReports(
        observations: [ExportCapabilityObservation],
        format: DocumentFormat
    ) throws -> [LossReport] {
        let matrix = try loadMatrix()
        return try observations.compactMap { observation in
            if structuralOnlyCapabilities.contains(observation.capability) { return nil }
            guard let row = matrix[observation.capability] else {
                throw ExportError.invalidPackage("형식 기능 행 누락: \(observation.capability)")
            }
            return try report(row.classification(for: format), observation, format)
        }
    }

    static func observedFrozenCombinations(
        project: DocumentProject
    ) throws -> [String] {
        try observedFrozenCombinations(observations: observedCapabilities(project: project))
    }

    static func observedFrozenCombinations(
        observations: [ExportCapabilityObservation]
    ) throws -> [String] {
        let grouped = Dictionary(grouping: observations, by: \.elementID)
        return frozenCombinations.filter { combination in
            let required = Set(combination.split(separator: "+").map(String.init))
            return grouped.values.contains { observations in
                required.isSubset(of: Set(observations.map(\.capability)))
            }
        }
    }
}
