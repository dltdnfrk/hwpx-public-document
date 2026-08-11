import Foundation

struct CompatibilitySourceContext {
    let corpus: CompatibilityCorpus
    let matrixByCapability: [String: FormatCapabilityRow]
    let projectsByFixture: [String: DocumentProject]
}

struct CompatibilityVerificationRequest {
    let receiptRoot: URL
    let observationRoot: URL
    let source: CompatibilitySourceContext
    let receipt: CompatibilityReceipt
}

private struct CompatibilityLocalArtifactRequest {
    let fixture: CompatibilityFixture
    let project: DocumentProject
    let format: DocumentFormat
    let receipt: CompatibilityReceipt
    let receiptRoot: URL
}

enum CompatibilityLocalEvidence {
    static func sourceContext() throws -> CompatibilitySourceContext {
        let resources = try resourceRoot()
        let compatibility = resources.appendingPathComponent("Compatibility", isDirectory: true)
        let corpus = try decode(
            CompatibilityCorpus.self,
            at: compatibility.appendingPathComponent("compatibility-corpus-1.0.0.json")
        )
        guard corpus.status == "frozen" else {
            throw CompatibilityEvidenceError.invalidCorpus("status must be frozen")
        }
        let matrix = try decode(
            FormatCapabilityResource.self,
            at: resources.appendingPathComponent("Capabilities/format-capabilities-1.0.0.json")
        )
        guard matrix.manifestVersion == corpus.manifestVersion else {
            throw CompatibilityEvidenceError.invalidCorpus("capability manifest version")
        }
        let matrixPairs = matrix.matrix.map { ($0.capability, $0) }
        guard Set(matrixPairs.map(\.0)).count == matrixPairs.count else {
            throw CompatibilityEvidenceError.invalidCorpus("duplicate capability matrix row")
        }
        var projects: [String: DocumentProject] = [:]
        for fixture in corpus.fixtures {
            let projectSource = compatibility.appendingPathComponent(fixture.projectPath)
            let projectData = try Data(contentsOf: projectSource)
            guard CompatibilityEvidenceFile.sha256(projectData) == fixture.projectHash else {
                throw CompatibilityEvidenceError.invalidCorpus("\(fixture.id) projectHash")
            }
            projects[fixture.id] = try JSONDecoder().decode(
                DocumentProject.self, from: projectData
            )
        }
        return CompatibilitySourceContext(
            corpus: corpus,
            matrixByCapability: Dictionary(uniqueKeysWithValues: matrixPairs),
            projectsByFixture: projects
        )
    }

    static func verificationContext(
        _ request: CompatibilityVerificationRequest
    ) throws -> CompatibilityVerificationContext {
        try validateLocalEvidence(
            receipt: request.receipt,
            source: request.source,
            receiptRoot: request.receiptRoot
        )
        return CompatibilityVerificationContext(
            receiptRoot: request.receiptRoot,
            observationRoot: request.observationRoot,
            requiredFonts: request.source.corpus.requiredFonts,
            visualTolerances: request.source.corpus.visualTolerances,
            expectedTextCountByFixture: request.source.projectsByFixture.mapValues(\.elements.count),
            structuralVerdict: .pass,
            semanticVerdict: .pass
        )
    }

    static func validationSnapshot(
        _ validation: FormatValidationReceipt
    ) -> CompatibilityArtifactValidation {
        CompatibilityArtifactValidation(
            structuralValid: validation.structuralValid,
            semanticValid: validation.semanticValid,
            evidenceSource: validation.evidenceSource.rawValue,
            validator: validation.validator,
            orderedElements: validation.orderedElements.map {
                CompatibilityValidatedElement(
                    elementID: $0.elementID,
                    kind: $0.kind,
                    order: $0.order,
                    textHash: $0.textHash
                )
            }
        )
    }

    private static func validateLocalEvidence(
        receipt: CompatibilityReceipt,
        source: CompatibilitySourceContext,
        receiptRoot: URL
    ) throws {
        guard receipt.corpusVersion == source.corpus.corpusVersion,
              receipt.manifestVersion == source.corpus.manifestVersion,
              receipt.requiredClientOperations == CompatibilityEvidenceGate.requiredClientOperations,
              let dispositions = receipt.dispositions
        else { throw CompatibilityEvidenceError.invalidCorpus("receipt contract") }
        var expectedGaps: [String: Set<String>] = [:]
        var expectedArtifactCount = 0
        for fixture in source.corpus.fixtures {
            guard let project = source.projectsByFixture[fixture.id] else {
                throw CompatibilityEvidenceError.invalidCorpus("\(fixture.id) project")
            }
            for format in fixture.formats {
                let reports = try ExportCapabilities.lossReports(project: project, format: format)
                for report in reports {
                    guard report.evidenceSource == .preflightPolicy,
                          source.matrixByCapability[report.capability]?.classification(for: format)
                            == report.classification.rawValue
                    else { throw CompatibilityEvidenceError.invalidCorpus("preflight policy report") }
                }
                let gaps = Array(Set(reports.filter {
                    $0.classification == .semanticLoss
                }.map(\.capability))).sorted()
                expectedGaps[format.rawValue, default: []].formUnion(gaps)
                let matches = dispositions.filter {
                    $0.fixtureID == fixture.id && $0.format == format
                }
                guard matches.count == 1,
                      let disposition = matches.first,
                      disposition.fixtureHash == fixture.projectHash,
                      disposition.capabilityGaps == gaps
                else { throw CompatibilityEvidenceError.invalidCorpus("disposition identity") }
                if gaps.isEmpty {
                    expectedArtifactCount += 1
                    guard disposition.disposition == .artifactValidated else {
                        throw CompatibilityEvidenceError.invalidCorpus("validated disposition")
                    }
                    try validateArtifact(
                        CompatibilityLocalArtifactRequest(
                            fixture: fixture,
                            project: project,
                            format: format,
                            receipt: receipt,
                            receiptRoot: receiptRoot
                        )
                    )
                } else {
                    guard disposition.disposition == .semanticLossBlocked,
                          !receipt.artifacts.contains(where: {
                              $0.fixtureID == fixture.id && $0.format == format
                          })
                    else { throw CompatibilityEvidenceError.invalidCorpus("semantic-loss disposition") }
                }
            }
        }
        let expectedDispositionCount = source.corpus.fixtures.reduce(0) {
            $0 + $1.formats.count
        }
        let normalizedGaps = expectedGaps.mapValues { $0.sorted() }.filter { !$0.value.isEmpty }
        guard dispositions.count == expectedDispositionCount,
              receipt.artifacts.count == expectedArtifactCount,
              receipt.capabilityGaps == normalizedGaps
        else { throw CompatibilityEvidenceError.invalidCorpus("fixture and format coverage") }
    }

    private static func validateArtifact(
        _ request: CompatibilityLocalArtifactRequest
    ) throws {
        let matches = request.receipt.artifacts.filter {
            $0.fixtureID == request.fixture.id && $0.format == request.format
        }
        guard matches.count == 1,
              let artifact = matches.first,
              artifact.fixtureHash == request.fixture.projectHash,
              let stored = artifact.validation
        else { throw CompatibilityEvidenceError.invalidCorpus("artifact receipt identity") }
        let data = try CompatibilityEvidenceFile.data(
            relativePath: artifact.relativePath,
            root: request.receiptRoot,
            kind: .artifact
        )
        guard CompatibilityEvidenceFile.sha256(data) == artifact.artifactHash,
              data.count == artifact.byteCount
        else { throw CompatibilityEvidenceError.invalidCorpus("artifact bytes are stale") }
        let fresh = try ExportArtifactValidator.validate(
            data: data, format: request.format, project: request.project
        )
        let snapshot = validationSnapshot(fresh)
        guard fresh.structuralValid,
              fresh.semanticValid,
              fresh.evidenceSource == .artifactDerived,
              stored.structuralValid == snapshot.structuralValid,
              stored.semanticValid == snapshot.semanticValid,
              stored.evidenceSource == snapshot.evidenceSource,
              stored.validator == snapshot.validator,
              stored.orderedElements == snapshot.orderedElements
        else { throw CompatibilityEvidenceError.invalidCorpus("artifact validation receipt") }
    }

    private static func resourceRoot() throws -> URL {
        let bundled = Bundle.main.resourceURL
        let local = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
            .appendingPathComponent("Resources", isDirectory: true)
        for candidate in [bundled, local].compactMap({ $0 }) where
            FileManager.default.fileExists(
                atPath: candidate.appendingPathComponent("Compatibility").path
            ) {
            return candidate
        }
        throw CompatibilityEvidenceError.invalidCorpus("Resources/Compatibility is missing")
    }

    private static func decode<Value: Decodable>(
        _ type: Value.Type,
        at source: URL
    ) throws -> Value {
        try JSONDecoder().decode(type, from: Data(contentsOf: source))
    }
}
