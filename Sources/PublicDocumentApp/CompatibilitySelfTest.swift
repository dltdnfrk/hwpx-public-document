import Foundation

enum CompatibilitySelfTest {
    static func run(at root: URL) throws -> CompatibilityReceipt {
        let source = try CompatibilityLocalEvidence.sourceContext()
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        var artifacts: [CompatibilityArtifact] = []
        var dispositions: [CompatibilityFormatDisposition] = []
        var gaps: [String: Set<String>] = [:]

        for fixture in source.corpus.fixtures {
            guard fixture.formats == DocumentFormat.allCases else {
                throw CompatibilityEvidenceError.invalidCorpus("\(fixture.id) formats")
            }
            guard let project = source.projectsByFixture[fixture.id] else {
                throw CompatibilityEvidenceError.invalidCorpus("\(fixture.id) project")
            }
            let fixtureRoot = root.appendingPathComponent(fixture.id, isDirectory: true)
            let exportReceipt = try DocumentExportEngine().export(
                project: project,
                request: ExportRequest(
                    operationID: "operation-ac07-local-\(fixture.id)",
                    destination: fixtureRoot,
                    formats: fixture.formats,
                    flatteningConsent: Set(fixture.formats)
                )
            )
            guard exportReceipt.selectedFormats == fixture.formats,
                  exportReceipt.allAuthoredElementIDsPreserved
            else {
                throw CompatibilityEvidenceError.invalidCorpus("\(fixture.id) export coverage")
            }

            for format in fixture.formats {
                let formatResults = exportReceipt.results.filter { $0.format == format }
                let published = exportReceipt.publishedFormats.contains(format)
                let blocked = exportReceipt.blockedFormats.contains(format)
                let formatReports = exportReceipt.lossReports.filter { $0.format == format }
                for report in formatReports {
                    guard report.evidenceSource == .preflightPolicy,
                          let row = source.matrixByCapability[report.capability],
                          row.classification(for: format) == report.classification.rawValue
                    else {
                        throw CompatibilityEvidenceError.invalidCorpus(
                            "\(fixture.id) \(format.rawValue) preflight policy report"
                        )
                    }
                }
                let semanticLossReports = formatReports.filter {
                    $0.classification == .semanticLoss
                }
                let actualGaps = Array(Set(semanticLossReports.map(\.capability))).sorted()
                gaps[format.rawValue, default: []].formUnion(actualGaps)
                if actualGaps.isEmpty {
                    guard published,
                          !blocked,
                          formatResults.count == 1,
                          let result = formatResults.first,
                          result.structuralValid,
                          result.semanticValid,
                          result.validation.evidenceSource == .artifactDerived
                    else {
                        throw CompatibilityEvidenceError.invalidCorpus(
                            "\(fixture.id) \(format.rawValue) validated artifact"
                        )
                    }
                    let relativePath = "\(fixture.id)/\(result.fileName)"
                    let artifactData = try Data(
                        contentsOf: root.appendingPathComponent(relativePath)
                    )
                    guard CompatibilityEvidenceFile.sha256(artifactData) == result.artifactHash,
                          artifactData.count == result.byteCount
                    else {
                        throw CompatibilityEvidenceError.invalidCorpus(
                            "\(fixture.id) \(format.rawValue) artifact identity"
                        )
                    }
                    artifacts.append(
                        CompatibilityArtifact(
                            fixtureID: fixture.id,
                            fixtureHash: fixture.projectHash,
                            format: format,
                            relativePath: relativePath,
                            artifactHash: result.artifactHash,
                            byteCount: result.byteCount,
                            validation: CompatibilityLocalEvidence.validationSnapshot(
                                result.validation
                            )
                        )
                    )
                    dispositions.append(
                        CompatibilityFormatDisposition(
                            fixtureID: fixture.id,
                            fixtureHash: fixture.projectHash,
                            format: format,
                            disposition: .artifactValidated,
                            capabilityGaps: []
                        )
                    )
                } else {
                    guard blocked,
                          !published,
                          formatResults.isEmpty,
                          !semanticLossReports.isEmpty
                    else {
                        throw CompatibilityEvidenceError.invalidCorpus(
                            "\(fixture.id) \(format.rawValue) semantic-loss block"
                        )
                    }
                    dispositions.append(
                        CompatibilityFormatDisposition(
                            fixtureID: fixture.id,
                            fixtureHash: fixture.projectHash,
                            format: format,
                            disposition: .semanticLossBlocked,
                            capabilityGaps: actualGaps
                        )
                    )
                }
            }
        }
        let preliminary = CompatibilityReceipt(
            corpusVersion: source.corpus.corpusVersion,
            manifestVersion: source.corpus.manifestVersion,
            structuralVerdict: .blocked,
            semanticVerdict: .blocked,
            visualVerdict: .blocked,
            clientVerdict: .blocked,
            overallVerdict: .blocked,
            requiredClientOperations: CompatibilityEvidenceGate.requiredClientOperations,
            capabilityGaps: gaps.mapValues { $0.sorted() }.filter { !$0.value.isEmpty },
            artifacts: artifacts,
            dispositions: dispositions,
            observations: [],
            visualObservations: [],
            externalBlockers: []
        )
        let gateContext = try CompatibilityLocalEvidence.verificationContext(
            CompatibilityVerificationRequest(
                receiptRoot: root,
                observationRoot: root,
                source: source,
                receipt: preliminary
            )
        )
        let receipt = try CompatibilityEvidenceGate.merging(
            receipt: preliminary, submission: .empty, context: gateContext
        )
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        let data = try encoder.encode(receipt)
        try data.write(
            to: root.appendingPathComponent("compatibility-receipt.json"),
            options: Data.WritingOptions.atomic
        )
        return receipt
    }

    static func verify(receipt: URL, observations: URL) throws -> CompatibilityReceipt {
        let base = try JSONDecoder().decode(
            CompatibilityReceipt.self, from: Data(contentsOf: receipt)
        )
        let supplied = try JSONDecoder().decode(
            CompatibilityEvidenceSubmission.self, from: Data(contentsOf: observations)
        )
        let source = try CompatibilityLocalEvidence.sourceContext()
        let context = try CompatibilityLocalEvidence.verificationContext(
            CompatibilityVerificationRequest(
                receiptRoot: receipt.deletingLastPathComponent(),
                observationRoot: observations.deletingLastPathComponent(),
                source: source,
                receipt: base
            )
        )
        return try CompatibilityEvidenceGate.merging(
            receipt: base, submission: supplied, context: context
        )
    }

}
