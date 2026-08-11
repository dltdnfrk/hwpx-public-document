import Foundation

enum CompatibilityBlockerValidation {
    private static let allowedCodes: Set<String> = [
        "console-locked",
        "required-client-unavailable",
        "authority-approval-pending",
    ]

    static func validate(
        _ blocker: CompatibilityExternalBlocker,
        receipt: CompatibilityReceipt,
        evidenceRoot: URL
    ) throws {
        guard !blocker.blockerID.isEmpty,
              !blocker.fixtureID.isEmpty,
              !blocker.operation.isEmpty,
              allowedCodes.contains(blocker.code),
              blocker.status == .blocked,
              ISO8601DateFormatter().date(from: blocker.observedAt) != nil,
              !blocker.detail.isEmpty,
              !blocker.evidence.isEmpty,
              Set(blocker.evidence.map(\.path)).count == blocker.evidence.count
        else { throw CompatibilityEvidenceError.invalidObservation("external blocker fields") }
        guard let artifact = receipt.artifacts.first(where: {
            $0.fixtureID == blocker.fixtureID && $0.format == blocker.format
        }), artifact.fixtureHash == blocker.fixtureHash,
        artifact.artifactHash == blocker.artifactHash else {
            throw CompatibilityEvidenceError.invalidObservation("external blocker identity")
        }
        switch blocker.verdictClass {
        case .visual:
            break
        case .client:
            guard CompatibilityEvidenceGate.requiredClientOperations[
                blocker.format.rawValue
            ]?.contains(blocker.operation) == true else {
                throw CompatibilityEvidenceError.invalidObservation(
                    "client blocker operation"
                )
            }
        }
        for reference in blocker.evidence {
            let data = try CompatibilityEvidenceFile.data(
                relativePath: reference.path,
                root: evidenceRoot,
                kind: .observation
            )
            guard CompatibilityEvidenceFile.sha256(data) == reference.sha256 else {
                throw CompatibilityEvidenceError.invalidObservation(
                    "external blocker evidence hash"
                )
            }
        }
    }
}
