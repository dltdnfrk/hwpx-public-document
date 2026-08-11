import Foundation

private struct CompatibilityObservationEnvironment {
    let name: String
    let version: String
    let build: String
    let osVersion: String
    let osBuild: String
    let fonts: [String]
    let timestamp: String
}

enum CompatibilityObservationAssessment {
    static func visual(
        _ observation: CompatibilityVisualObservation,
        context: CompatibilityVerificationContext
    ) throws -> CompatibilityVerdict {
        try validateEnvironment(
            CompatibilityObservationEnvironment(
                name: observation.clientName,
                version: observation.clientVersion,
                build: observation.clientBuild,
                osVersion: observation.osVersion,
                osBuild: observation.osBuild,
                fonts: observation.fonts,
                timestamp: observation.timestamp
            )
        )
        let evidenceComplete = try validateEvidence(
            path: observation.evidencePath,
            hash: observation.evidenceHash,
            root: context.observationRoot
        )
        let tolerance = context.visualTolerances
        if !Set(context.requiredFonts).isSubset(of: Set(observation.fonts)) { return .fail }
        if let expected = observation.expectedPageCount, expected <= 0 {
            throw CompatibilityEvidenceError.invalidObservation("expectedPageCount")
        }
        if let observed = observation.observedPageCount, observed <= 0 { return .fail }
        if let expected = observation.expectedPageCount,
           let observed = observation.observedPageCount,
           abs(observed - expected) > tolerance.pageCountDelta { return .fail }
        if let missing = observation.missingAuthoredElementIDs,
           missing.count > tolerance.missingTextElements { return .fail }
        if let blanks = observation.unexpectedBlankPageNumbers,
           blanks.count > tolerance.unexpectedBlankPages { return .fail }
        if let coverage = observation.textBoundsCoverage {
            guard coverage.isFinite, (0.0...1.0).contains(coverage) else {
                throw CompatibilityEvidenceError.invalidObservation("textBoundsCoverage")
            }
            if coverage < tolerance.minimumTextBoundsCoverage { return .fail }
        }
        guard evidenceComplete,
              observation.expectedPageCount != nil,
              observation.observedPageCount != nil,
              observation.missingAuthoredElementIDs != nil,
              observation.unexpectedBlankPageNumbers != nil,
              observation.textBoundsCoverage != nil,
              !observation.toolID.isEmpty
        else { return .blocked }
        return .pass
    }

    static func client(
        _ observation: CompatibilityObservation,
        expectedTextCount: Int,
        context: CompatibilityVerificationContext
    ) throws -> CompatibilityVerdict {
        try validateEnvironment(
            CompatibilityObservationEnvironment(
                name: observation.clientName,
                version: observation.clientVersion,
                build: observation.clientBuild,
                osVersion: observation.osVersion,
                osBuild: observation.osBuild,
                fonts: observation.fonts,
                timestamp: observation.timestamp
            )
        )
        let evidenceComplete = try validateEvidence(
            path: observation.evidencePath,
            hash: observation.evidenceHash,
            root: context.observationRoot
        )
        let tolerance = context.visualTolerances
        if !Set(context.requiredFonts).isSubset(of: Set(observation.fonts)) { return .fail }
        if observation.opened == false { return .fail }
        if let warnings = observation.extensionWarningCount, warnings != 0 { return .fail }
        if let expected = observation.expectedTextCount, expected != expectedTextCount {
            throw CompatibilityEvidenceError.invalidObservation("expectedTextCount")
        }
        if let expected = observation.expectedTextCount,
           let observed = observation.observedTextCount,
           observed != expected { return .fail }
        if let expected = observation.expectedPageCount, expected <= 0 {
            throw CompatibilityEvidenceError.invalidObservation("expectedPageCount")
        }
        if let observed = observation.observedPageCount, observed <= 0 { return .fail }
        if let expected = observation.expectedPageCount,
           let observed = observation.observedPageCount,
           abs(observed - expected) > tolerance.pageCountDelta { return .fail }
        if let blanks = observation.unexpectedBlankPageCount,
           blanks > tolerance.unexpectedBlankPages { return .fail }
        guard evidenceComplete,
              observation.opened != nil,
              observation.extensionWarningCount != nil,
              observation.expectedTextCount != nil,
              observation.observedTextCount != nil,
              observation.expectedPageCount != nil,
              observation.observedPageCount != nil,
              observation.unexpectedBlankPageCount != nil
        else { return .blocked }
        return .pass
    }

    private static func validateEnvironment(
        _ environment: CompatibilityObservationEnvironment
    ) throws {
        guard !environment.name.isEmpty,
              !environment.version.isEmpty,
              !environment.build.isEmpty,
              !environment.osVersion.isEmpty,
              !environment.osBuild.isEmpty,
              !environment.fonts.isEmpty,
              !environment.timestamp.isEmpty
        else {
            throw CompatibilityEvidenceError.invalidObservation(
                "exact client, OS, font, and timestamp fields are required"
            )
        }
    }

    private static func validateEvidence(
        path: String?,
        hash: String?,
        root: URL
    ) throws -> Bool {
        guard let path, let hash else { return false }
        let data = try CompatibilityEvidenceFile.data(
            relativePath: path, root: root, kind: .observation
        )
        guard CompatibilityEvidenceFile.sha256(data) == hash else {
            throw CompatibilityEvidenceError.invalidObservation("evidenceHash mismatch")
        }
        return true
    }
}
