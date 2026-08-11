import Foundation

struct CompatibilityVerificationContext {
    let receiptRoot: URL
    let observationRoot: URL
    let requiredFonts: [String]
    let visualTolerances: CompatibilityVisualTolerances
    let expectedTextCountByFixture: [String: Int]
    let structuralVerdict: CompatibilityVerdict
    let semanticVerdict: CompatibilityVerdict
}

private struct CompatibilityVisualKey: Hashable {
    let fixtureID: String
    let format: DocumentFormat
}

private struct CompatibilityClientKey: Hashable {
    let fixtureID: String
    let format: DocumentFormat
    let operation: String
}

private struct CompatibilityArtifactReference {
    let fixtureID: String
    let fixtureHash: String
    let format: DocumentFormat
    let artifactHash: String
}

private struct CompatibilityGateInput {
    let receipt: CompatibilityReceipt
    let visualObservations: [CompatibilityVisualObservation]
    let clientObservations: [CompatibilityObservation]
    let blockers: [CompatibilityExternalBlocker]
    let context: CompatibilityVerificationContext
}

enum CompatibilityEvidenceGate {
    static let requiredClientOperations: [String: [String]] = [
        "hwpx": ["hancom-official-reopen", "polaris-office-reopen"],
        "hwp": ["hancom-official-reopen", "polaris-office-reopen"],
        "docx": ["genoffice-docs-reopen", "microsoft-word-reopen"],
        "markdown": ["approved-rendering", "commonmark-validate"],
    ]
    private static let clientByOperation: [String: String] = [
        "hancom-official-reopen": "hancom-official",
        "polaris-office-reopen": "polaris-office",
        "genoffice-docs-reopen": "genoffice-docs",
        "microsoft-word-reopen": "microsoft-word",
        "approved-rendering": "public-document-rendering-authority",
        "commonmark-validate": "commonmark-validator",
    ]

    static func merging(
        receipt: CompatibilityReceipt,
        submission: CompatibilityEvidenceSubmission,
        context: CompatibilityVerificationContext
    ) throws -> CompatibilityReceipt {
        guard receipt.requiredClientOperations == requiredClientOperations else {
            throw CompatibilityEvidenceError.invalidCorpus("required client operations")
        }
        let input = CompatibilityGateInput(
            receipt: receipt,
            visualObservations: (receipt.visualObservations ?? []) + submission.visualObservations,
            clientObservations: receipt.observations + submission.clientObservations,
            blockers: (receipt.externalBlockers ?? []) + submission.externalBlockers,
            context: context
        )
        try requireUniqueIDs(
            input.visualObservations.map(\.observationID)
                + input.clientObservations.map(\.observationID),
            field: "observationID"
        )
        try requireUniqueIDs(input.blockers.map(\.blockerID), field: "blockerID")
        for blocker in input.blockers {
            try CompatibilityBlockerValidation.validate(
                blocker,
                receipt: receipt,
                evidenceRoot: context.observationRoot
            )
        }
        let visual = try visualVerdict(input)
        let client = try clientVerdict(input)
        let verdicts = [context.structuralVerdict, context.semanticVerdict, visual, client]
        let overall: CompatibilityVerdict
        if verdicts.contains(.fail) {
            overall = .fail
        } else if verdicts.allSatisfy({ $0 == .pass }) {
            overall = .pass
        } else {
            overall = .blocked
        }
        return CompatibilityReceipt(
            corpusVersion: receipt.corpusVersion,
            manifestVersion: receipt.manifestVersion,
            structuralVerdict: context.structuralVerdict,
            semanticVerdict: context.semanticVerdict,
            visualVerdict: visual,
            clientVerdict: client,
            overallVerdict: overall,
            requiredClientOperations: requiredClientOperations,
            capabilityGaps: receipt.capabilityGaps,
            artifacts: receipt.artifacts,
            dispositions: receipt.dispositions,
            observations: input.clientObservations,
            visualObservations: input.visualObservations,
            externalBlockers: input.blockers
        )
    }

    private static func visualVerdict(
        _ input: CompatibilityGateInput
    ) throws -> CompatibilityVerdict {
        let required = Set(input.receipt.artifacts.map {
            CompatibilityVisualKey(fixtureID: $0.fixtureID, format: $0.format)
        })
        var assessments: [CompatibilityVisualKey: [CompatibilityVerdict]] = [:]
        for observation in input.visualObservations {
            let artifact = try boundArtifact(
                CompatibilityArtifactReference(
                    fixtureID: observation.fixtureID,
                    fixtureHash: observation.fixtureHash,
                    format: observation.format,
                    artifactHash: observation.artifactHash
                ),
                receipt: input.receipt
            )
            let key = CompatibilityVisualKey(
                fixtureID: artifact.fixtureID, format: artifact.format
            )
            assessments[key, default: []].append(
                try CompatibilityObservationAssessment.visual(
                    observation, context: input.context
                )
            )
        }
        return aggregate(
            required: required,
            assessments: assessments,
            hasBlocker: input.blockers.contains { $0.verdictClass == .visual }
        )
    }

    private static func clientVerdict(
        _ input: CompatibilityGateInput
    ) throws -> CompatibilityVerdict {
        let required = Set(input.receipt.artifacts.flatMap { artifact in
            requiredClientOperations[artifact.format.rawValue, default: []].map {
                CompatibilityClientKey(
                    fixtureID: artifact.fixtureID, format: artifact.format, operation: $0
                )
            }
        })
        var assessments: [CompatibilityClientKey: [CompatibilityVerdict]] = [:]
        for observation in input.clientObservations {
            let artifact = try boundArtifact(
                CompatibilityArtifactReference(
                    fixtureID: observation.fixtureID,
                    fixtureHash: observation.fixtureHash,
                    format: observation.format,
                    artifactHash: observation.artifactHash
                ),
                receipt: input.receipt
            )
            guard requiredClientOperations[artifact.format.rawValue]?.contains(
                observation.operation
            ) == true,
            clientByOperation[observation.operation] == observation.clientID,
            let expectedTextCount = input.context.expectedTextCountByFixture[observation.fixtureID]
            else { throw CompatibilityEvidenceError.invalidObservation("required operation owner") }
            let key = CompatibilityClientKey(
                fixtureID: artifact.fixtureID,
                format: artifact.format,
                operation: observation.operation
            )
            assessments[key, default: []].append(
                try CompatibilityObservationAssessment.client(
                    observation,
                    expectedTextCount: expectedTextCount,
                    context: input.context
                )
            )
        }
        return aggregate(
            required: required,
            assessments: assessments,
            hasBlocker: input.blockers.contains { $0.verdictClass == .client }
        )
    }

    private static func aggregate<Key: Hashable>(
        required: Set<Key>,
        assessments: [Key: [CompatibilityVerdict]],
        hasBlocker: Bool
    ) -> CompatibilityVerdict {
        if assessments.values.flatMap({ $0 }).contains(.fail) { return .fail }
        if hasBlocker { return .blocked }
        return required.allSatisfy {
            assessments[$0]?.contains(.pass) == true
        } ? .pass : .blocked
    }

    private static func boundArtifact(
        _ reference: CompatibilityArtifactReference,
        receipt: CompatibilityReceipt
    ) throws -> CompatibilityArtifact {
        guard let artifact = receipt.artifacts.first(where: {
            $0.fixtureID == reference.fixtureID && $0.format == reference.format
        }) else { throw CompatibilityEvidenceError.invalidObservation("fixtureID and format") }
        guard artifact.fixtureHash == reference.fixtureHash else {
            throw CompatibilityEvidenceError.invalidObservation("fixtureHash mismatch")
        }
        guard artifact.artifactHash == reference.artifactHash else {
            throw CompatibilityEvidenceError.invalidObservation("artifactHash mismatch")
        }
        return artifact
    }

    private static func requireUniqueIDs(_ ids: [String], field: String) throws {
        guard !ids.contains(where: \.isEmpty), Set(ids).count == ids.count else {
            throw CompatibilityEvidenceError.invalidObservation("duplicate or empty \(field)")
        }
    }
}
