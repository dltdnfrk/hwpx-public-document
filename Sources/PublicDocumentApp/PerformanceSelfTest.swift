import Foundation

struct PerformanceExecutionIdentity: Encodable {
    let bundleIdentifier: String
    let bundleVersion: String
    let applicationVersion: String
    let bundleExecutableRelativePath: String
    let executableSHA256: String
    let genOfficeRuntimeManifestRelativePath: String
    let genOfficeRuntimeManifestSHA256: String
    let genOfficeBundleRelativePath: String
    let genOfficeBundleSHA256: String
    let nodeExecutableRelativePath: String
    let nodeExecutableSHA256: String
    let rhwpExecutableRelativePath: String
    let rhwpExecutableSHA256: String
}

struct PerformanceEvidenceReceipt: Encodable {
    let profileVersion: String
    let profileHash: String
    let executionIdentity: PerformanceExecutionIdentity
    let environment: PerformanceEnvironment
    let fixtures: [PerformanceFixtureObservation]
    let exportObservations: [PerformanceExportObservation]
    let interactionObservation: PerformanceInteractionObservation
    let uiObservation: PerformanceUIObservation
    let overallVerdict: String
}

enum PerformanceSelfTest {
    static func run(at root: URL) throws -> PerformanceEvidenceReceipt {
        let executionIdentity = try executionIdentity()
        let profileData = try Data(contentsOf: profileURL())
        let profile = try JSONDecoder().decode(PerformanceProfile.self, from: profileData)
        guard
            let largeFixtureRequirement = profile.fixtures["50-mb"],
            let minimumAuthoredUTF8Bytes = largeFixtureRequirement.minimumAuthoredUTF8Bytes,
            let elementChunkBytes = largeFixtureRequirement.elementChunkBytes,
            let minimumPages = profile.fixtures["100-page"]?.minimumPageCount,
            let pageFixtureElementCount = profile.fixtures["100-page"]?.elementCount
        else {
            throw ExportError.invalidPackage("성능 시험 fixture 기준")
        }
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        let fixtures = [
            PerformanceFixtures.hundredPage(elementCount: pageFixtureElementCount),
            try PerformanceFixtures.fiftyMegabytes(
                minimumAuthoredUTF8Bytes: minimumAuthoredUTF8Bytes,
                elementChunkBytes: elementChunkBytes
            ),
        ]
        guard fixtures[0].declaredPageCount == minimumPages,
              fixtures[0].project.elements.count == pageFixtureElementCount else {
            throw ExportError.invalidPackage("100쪽 fixture")
        }

        var fixtureObservations: [PerformanceFixtureObservation] = []
        var exportObservations: [PerformanceExportObservation] = []
        for fixture in fixtures {
            guard let requirement = profile.fixtures[fixture.fixtureID] else {
                throw ExportError.invalidPackage("성능 시험 fixture 프로필")
            }
            let fixtureObservation = try PerformanceFixtures.observation(
                fixture: fixture,
                requirement: requirement
            )
            guard fixtureObservation.snapshotThresholdPassed,
                  fixtureObservation.authoredUTF8ThresholdPassed else {
                throw ExportError.invalidPackage("성능 시험 fixture 크기 기준")
            }
            fixtureObservations.append(fixtureObservation)
            for format in profile.formats {
                let destination = root
                    .appendingPathComponent("artifacts", isDirectory: true)
                    .appendingPathComponent(fixture.fixtureID, isDirectory: true)
                    .appendingPathComponent(format.rawValue, isDirectory: true)
                let measured = try measureExport(
                    project: fixture.project,
                    fixtureID: fixture.fixtureID,
                    format: format,
                    destination: destination
                )
                guard let result = measured.receipt.results.first else {
                    throw ExportError.invalidPackage("성능 시험 결과 \(format.rawValue)")
                }
                let artifactPath = destination.appendingPathComponent(result.fileName)
                let pageValidationStart = ProcessInfo.processInfo.systemUptime
                let observedPageCount: Int?
                if fixture.fixtureID == "100-page" {
                    observedPageCount = try renderedPageCount(format: format, artifact: artifactPath)
                } else {
                    observedPageCount = nil
                }
                let authoredContent = try PerformanceFixtures.validateAuthoredContent(
                    artifact: artifactPath,
                    project: fixture.project,
                    result: result
                )
                let duration = measured.durationSeconds
                    + ProcessInfo.processInfo.systemUptime - pageValidationStart
                let pageCountPassed = fixture.fixtureID != "100-page"
                    || observedPageCount == nil
                    || observedPageCount == minimumPages
                exportObservations.append(PerformanceExportObservation(
                    operationID: measured.receipt.operationID,
                    fixtureID: fixture.fixtureID,
                    format: format,
                    snapshotHash: measured.receipt.snapshotHash,
                    durationSeconds: duration,
                    renderedPageCount: observedPageCount,
                    artifactRelativePath: "artifacts/\(fixture.fixtureID)/\(format.rawValue)/\(result.fileName)",
                    artifactHash: result.artifactHash,
                    artifactByteCount: result.byteCount,
                    authoredUTF8ByteCount: authoredContent.payload.utf8ByteCount,
                    authoredContentHash: authoredContent.payload.contentHash,
                    authoredContentValidator: authoredContent.validator,
                    authoredContentValidated: authoredContent.valid,
                    structuralValid: result.structuralValid,
                    semanticValid: result.semanticValid,
                    validator: result.validator,
                    passed: duration <= profile.thresholds.exportSeconds
                        && result.structuralValid && result.semanticValid
                        && pageCountPassed && authoredContent.valid
                ))
            }
        }
        let benchmark = try PerformanceInteractionBenchmark.run(
            root: root.appendingPathComponent("interaction", isDirectory: true),
            profile: profile
        )
        let interaction = benchmark.interactionObservation
        let passed = exportObservations.allSatisfy(\.passed)
            && interaction.responsive
            && interaction.progressPassed
            && interaction.cancellationPassed
            && benchmark.uiObservation.status == "pass"
        let overallVerdict = benchmark.uiObservation.status == "blocked"
            ? "blocked"
            : (passed ? "pass" : "fail")
        let receipt = PerformanceEvidenceReceipt(
            profileVersion: profile.profileVersion,
            profileHash: hash(profileData),
            executionIdentity: executionIdentity,
            environment: environment(),
            fixtures: fixtureObservations,
            exportObservations: exportObservations,
            interactionObservation: interaction,
            uiObservation: benchmark.uiObservation,
            overallVerdict: overallVerdict
        )
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        try encoder.encode(receipt).write(
            to: root.appendingPathComponent("performance-receipt.json"),
            options: .atomic
        )
        return receipt
    }

    private static func measureExport(
        project: DocumentProject,
        fixtureID: String,
        format: DocumentFormat,
        destination: URL
    ) throws -> MeasuredExport {
        let start = ProcessInfo.processInfo.systemUptime
        var previousHeartbeat = start
        var maximumGap = 0.0
        var heartbeatCount = 0
        let timer = Timer.scheduledTimer(withTimeInterval: 0.01, repeats: true) { _ in
            let now = ProcessInfo.processInfo.systemUptime
            maximumGap = max(maximumGap, (now - previousHeartbeat) * 1000)
            previousHeartbeat = now
            heartbeatCount += 1
        }
        let group = DispatchGroup()
        let outcome = PerformanceExportOutcomeBox()
        group.enter()
        DispatchQueue.global(qos: .userInitiated).async {
            let result = Result {
                try DocumentExportEngine().export(
                    project: project,
                    request: ExportRequest(
                        operationID: "performance-\(fixtureID)-\(format.rawValue)",
                        destination: destination,
                        formats: [format],
                        flatteningConsent: [format]
                    )
                )
            }
            outcome.finish(result)
            group.leave()
        }
        while group.wait(timeout: .now()) == .timedOut {
            _ = RunLoop.current.run(mode: .default, before: Date(timeIntervalSinceNow: 0.005))
        }
        timer.invalidate()
        let duration = ProcessInfo.processInfo.systemUptime - start
        if heartbeatCount == 0 { maximumGap = duration * 1000 }
        return MeasuredExport(
            receipt: try outcome.value(),
            durationSeconds: duration,
            heartbeatCount: heartbeatCount,
            maximumHeartbeatGapMilliseconds: maximumGap
        )
    }
}
