import CryptoKit
import Darwin
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

    private static func executionIdentity() throws -> PerformanceExecutionIdentity {
        let bundle = Bundle.main
        let appRoot = bundle.bundleURL.standardizedFileURL
        guard appRoot.pathExtension == "app",
              bundle.bundleIdentifier == "com.muni.public-document" else {
            throw ExportError.invalidPackage("AC-09 성능 증거는 패키지된 PublicDocument.app에서 실행해야 합니다.")
        }
        let executableRelativePath = "Contents/MacOS/PublicDocumentApp"
        let genOfficeManifestRelativePath = "Contents/Resources/GenOffice/runtime-manifest.json"
        let genOfficeBundleRelativePath = "Contents/Resources/GenOffice/public-document-genoffice.js"
        let nodeRelativePath = "Contents/Resources/Engines/node"
        let rhwpRelativePath = "Contents/Resources/Engines/rhwp"
        let executable = appRoot.appendingPathComponent(executableRelativePath)
        guard bundle.executableURL?.resolvingSymlinksInPath().standardizedFileURL
                == executable.resolvingSymlinksInPath().standardizedFileURL else {
            throw ExportError.invalidPackage("AC-09 패키지 실행 파일 경로")
        }
        return PerformanceExecutionIdentity(
            bundleIdentifier: bundle.bundleIdentifier ?? "unavailable",
            bundleVersion: bundle.object(forInfoDictionaryKey: "CFBundleVersion") as? String
                ?? "unavailable",
            applicationVersion: bundle.object(
                forInfoDictionaryKey: "CFBundleShortVersionString"
            ) as? String ?? "unavailable",
            bundleExecutableRelativePath: executableRelativePath,
            executableSHA256: try hashFile(executable),
            genOfficeRuntimeManifestRelativePath: genOfficeManifestRelativePath,
            genOfficeRuntimeManifestSHA256: try hashFile(
                appRoot.appendingPathComponent(genOfficeManifestRelativePath)
            ),
            genOfficeBundleRelativePath: genOfficeBundleRelativePath,
            genOfficeBundleSHA256: try hashFile(
                appRoot.appendingPathComponent(genOfficeBundleRelativePath)
            ),
            nodeExecutableRelativePath: nodeRelativePath,
            nodeExecutableSHA256: try hashFile(appRoot.appendingPathComponent(nodeRelativePath)),
            rhwpExecutableRelativePath: rhwpRelativePath,
            rhwpExecutableSHA256: try hashFile(appRoot.appendingPathComponent(rhwpRelativePath))
        )
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

    private static func profileURL() -> URL {
        let bundled = Bundle.main.resourceURL?
            .appendingPathComponent("Performance/performance-profile-1.0.0.json")
        let local = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
            .appendingPathComponent("Resources/Performance/performance-profile-1.0.0.json")
        return bundled.flatMap { FileManager.default.fileExists(atPath: $0.path) ? $0 : nil } ?? local
    }

    private static func renderedPageCount(format: DocumentFormat, artifact: URL) throws -> Int? {
        guard [.hwpx, .hwp].contains(format) else { return nil }
        let bundled = Bundle.main.resourceURL?.appendingPathComponent("Engines/rhwp")
        let local = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
            .appendingPathComponent("Resources/Engines/rhwp")
        let engine = bundled.flatMap {
            FileManager.default.isExecutableFile(atPath: $0.path) ? $0 : nil
        } ?? local
        let process = Process()
        let output = Pipe()
        process.executableURL = engine
        process.arguments = ["info", artifact.path, "--json"]
        process.standardOutput = output
        process.standardError = FileHandle.standardError
        try process.run()
        let data = output.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        guard process.terminationStatus == 0 else {
            throw ExportError.rhwpFailed("성능 fixture 쪽수 검증 실패")
        }
        return try JSONDecoder().decode(RhwpPageInfo.self, from: data).pageCount
    }

    private static func environment() -> PerformanceEnvironment {
        #if arch(arm64)
        let architecture = "arm64"
        #else
        let architecture = "unsupported"
        #endif
        return PerformanceEnvironment(
            modelIdentifier: sysctlString("hw.model"),
            processor: sysctlString("machdep.cpu.brand_string"),
            architecture: architecture,
            physicalMemoryBytes: ProcessInfo.processInfo.physicalMemory,
            osVersion: ProcessInfo.processInfo.operatingSystemVersionString,
            osBuild: sysctlString("kern.osversion"),
            applicationVersion: Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "0.1.0",
            recordedAt: ISO8601DateFormatter().string(from: Date())
        )
    }

    private static func sysctlString(_ name: String) -> String {
        var size = 0
        guard sysctlbyname(name, nil, &size, nil, 0) == 0, size > 0 else { return "unavailable" }
        var value = [CChar](repeating: 0, count: size)
        guard sysctlbyname(name, &value, &size, nil, 0) == 0 else { return "unavailable" }
        return String(cString: value)
    }

    private static func hash(_ data: Data) -> String {
        "sha256:" + SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }

    private static func hashFile(_ url: URL) throws -> String {
        guard FileManager.default.isReadableFile(atPath: url.path) else {
            throw ExportError.invalidPackage("AC-09 패키지 런타임 파일: \(url.lastPathComponent)")
        }
        return hash(try Data(contentsOf: url))
    }
}
