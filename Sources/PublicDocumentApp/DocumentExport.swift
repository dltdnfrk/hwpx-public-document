import CryptoKit
import Foundation

final class DocumentExportEngine {
    private let fileManager: FileManager

    init(fileManager: FileManager = .default) {
        self.fileManager = fileManager
    }

    func export(project: DocumentProject, request: ExportRequest) throws -> ExportReceipt {
        guard !request.formats.isEmpty else { throw ExportError.noFormatSelected }
        let authoredElementsValid = try validatesAuthorableElements(project)
        guard authoredElementsValid else {
            throw ExportError.invalidPackage("작성 요소 ID가 비어 있거나 중복되었습니다")
        }
        let observedCapabilities = try FormatCapabilityPolicy.observedCapabilities(project: project)
        let observedFrozenCombinations = try FormatCapabilityPolicy.observedFrozenCombinations(
            observations: observedCapabilities
        )
        try fileManager.createDirectory(at: request.destination, withIntermediateDirectories: true)
        let snapshotData = try JSONEncoder.sorted.encode(project)
        let snapshotHash = sha256(snapshotData)
        let selected = DocumentFormat.allCases.filter(request.formats.contains)
        var published: [DocumentFormat] = []
        var blocked: [DocumentFormat] = []
        var failed: [DocumentFormat] = []
        var failures: [ExportFailureDisposition] = []
        var results: [ExportResult] = []
        var lossReports: [LossReport] = []
        var consentRecorded = false
        var consentFormats: [DocumentFormat] = []

        for format in selected {
            let reports = try FormatCapabilityPolicy.lossReports(
                observations: observedCapabilities,
                format: format
            )
            lossReports.append(contentsOf: reports)
            let hasSemanticLoss = reports.contains { $0.classification == .semanticLoss }
            let needsConsent = reports.contains { $0.classification == .visualOnlyFlattening }
            let hasConsent = needsConsent && request.flatteningConsent.contains(format)
            if hasConsent {
                consentRecorded = true
                consentFormats.append(format)
            }
            if hasSemanticLoss || (needsConsent && !hasConsent) {
                blocked.append(format)
                continue
            }
            do {
                let result = try exportOne(
                    project: project,
                    destination: request.destination,
                    format: format
                )
                published.append(format)
                results.append(result)
            } catch let failure as ExportStageFailure {
                failed.append(format)
                failures.append(failure.disposition)
            }
        }

        TypstSidecar.write(project: project, destination: request.destination)
        return ExportReceipt(
            operationID: request.operationID,
            snapshotRevisionID: project.currentRevisionID,
            snapshotHash: snapshotHash,
            fixtureHash: snapshotHash,
            selectedFormats: selected,
            publishedFormats: published,
            blockedFormats: blocked,
            failedFormats: failed,
            failures: failures,
            results: results,
            lossReports: lossReports.sorted {
                if $0.classification != $1.classification {
                    return $0.classification == .semanticLoss
                }
                return $0.elementPath < $1.elementPath
            },
            observedCapabilities: observedCapabilities,
            observedFrozenCombinations: observedFrozenCombinations,
            flatteningConsentRecorded: consentRecorded,
            flatteningConsentFormats: consentFormats,
            allAuthoredElementIDsPreserved: authoredElementsValid,
            rhwpCommit: ExportCapabilities.rhwpCommit
        )
    }

    private func exportOne(
        project: DocumentProject,
        destination: URL,
        format: DocumentFormat
    ) throws -> ExportResult {
        let fileName = "ac05-fixture.\(format.fileExtension)"
        let output = destination.appendingPathComponent(fileName)
        guard !fileManager.fileExists(atPath: output.path) else {
            throw ExportStageFailure(disposition: ExportFailureDisposition(
                format: format,
                stage: .destination,
                error: ExportError.destinationExists(fileName)
            ))
        }
        let data: Data
        let engineIdentity: ExportEngineIdentity?
        do {
            switch format {
            case .hwpx:
                data = try RhwpExportAdapter(fileManager: fileManager).export(
                    project: project,
                    format: format,
                    workingDirectory: destination
                )
                engineIdentity = nil
            case .hwp:
                data = try RhwpExportAdapter(fileManager: fileManager).export(
                    project: project,
                    format: format,
                    workingDirectory: destination
                )
                engineIdentity = nil
            case .docx:
                guard let revision = project.revisions.first(where: {
                    $0.revisionID == project.currentRevisionID
                }) else {
                    throw ExportError.invalidPackage("현재 리비전의 생성 시각을 찾을 수 없습니다")
                }
                let normalized = try GenOfficeDocxAdapter(fileManager: fileManager).normalize(
                    seed: ExportSerializers.docx(project: project),
                    workingDirectory: destination,
                    savedAt: revision.createdAt
                )
                data = normalized.data
                engineIdentity = normalized.engineIdentity
            case .markdown:
                data = try ExportSerializers.markdown(project: project)
                engineIdentity = nil
            }
        } catch {
            throw ExportStageFailure(disposition: ExportFailureDisposition(
                format: format,
                stage: .adapter,
                error: error
            ))
        }
        let validation: FormatValidationReceipt
        do {
            validation = try ExportArtifactValidator.validate(
                data: data,
                format: format,
                project: project
            )
        } catch {
            throw ExportStageFailure(disposition: ExportFailureDisposition(
                format: format,
                stage: .validation,
                error: error
            ))
        }
        do {
            try publish(data: data, to: output)
        } catch {
            throw ExportStageFailure(disposition: ExportFailureDisposition(
                format: format,
                stage: .destination,
                error: error
            ))
        }
        return ExportResult(
            format: format,
            fileName: fileName,
            relativePath: fileName,
            artifactHash: sha256(data),
            byteCount: data.count,
            structuralValid: validation.structuralValid,
            semanticValid: validation.semanticValid,
            validator: validation.validator,
            validation: validation,
            engineIdentity: engineIdentity
        )
    }

    private func validatesAuthorableElements(_ project: DocumentProject) throws -> Bool {
        let ids = project.elements.map(\.elementID)
        guard Set(ids).count == ids.count, !ids.contains(where: { $0.isEmpty }) else { return false }
        for element in project.elements where !ExportCapabilities.authorableKinds.contains(element.kind) {
            throw ExportError.unsupportedElementKind(element.kind)
        }
        return true
    }

    private func publish(data: Data, to output: URL) throws {
        let temporary = output.deletingLastPathComponent()
            .appendingPathComponent(".\(output.lastPathComponent).\(UUID().uuidString).tmp")
        do {
            try data.write(to: temporary, options: .withoutOverwriting)
            try fileManager.moveItem(at: temporary, to: output)
        } catch {
            try? fileManager.removeItem(at: temporary)
            throw error
        }
    }

    private func sha256(_ data: Data) -> String {
        "sha256:" + SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }
}

private struct ExportStageFailure: Error {
    let disposition: ExportFailureDisposition
}

private extension JSONEncoder {
    static var sorted: JSONEncoder {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        return encoder
    }
}
