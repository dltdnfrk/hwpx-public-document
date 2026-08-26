import Foundation

final class BatchExportCoordinator {
    private static let progressTotal = 4
    private let fileManager: FileManager
    private let store: BatchExportStore

    init(fileManager: FileManager = .default) {
        self.fileManager = fileManager
        store = BatchExportStore(fileManager: fileManager)
    }

    func run(
        request: BatchExportRequest,
        execution: BatchExportExecution = .normal,
        cancellation: BatchExportCancellation? = nil,
        progress: (BatchExportManifest) -> Void = { _ in }
    ) throws -> BatchExportManifest {
        guard !request.formats.isEmpty else { throw ExportError.noFormatSelected }
        try fileManager.createDirectory(at: request.destination, withIntermediateDirectories: true)
        let operationRoot = store.operationRoot(for: request.destination, operationID: request.operationID)
        guard !fileManager.fileExists(atPath: operationRoot.path) else {
            throw BatchExportError.duplicateOperation(request.operationID)
        }
        try store.prepare(operationRoot)
        try injectBeforeInitialManifest(execution.fault)
        let selectedFormats = DocumentFormat.allCases.filter(request.formats.contains)
        var manifest = try store.initialManifest(
            request: request,
            operationRoot: operationRoot,
            selectedFormats: selectedFormats
        )
        try store.persist(manifest, at: operationRoot)
        progress(manifest)

        var publishedCount = 0
        for index in manifest.items.indices {
            let reachedTestLimit = execution.cancelAfterPublishedCount.map {
                publishedCount >= $0
            } ?? false
            if reachedTestLimit || cancellation?.isCancelled() == true {
                manifest = cancelRemaining(manifest, startingAt: index)
                try store.cleanupStaging(operationRoot)
                manifest = manifest.updating(state: .cancelled, cleanupState: .clean)
                try store.persist(manifest, at: operationRoot)
                progress(manifest)
                return manifest
            }
            let item = manifest.items[index]
            manifest = replacing(
                manifest,
                at: index,
                with: item.updating(state: .exporting, progressCompleted: 2)
            )
            try store.persist(manifest, at: operationRoot)
            progress(manifest)
            do {
                try injectProcessFailure(execution.fault, item: item)
                guard let project = request.documents.first(where: {
                    $0.project.documentID == item.documentID
                })?.project else {
                    throw BatchExportError.missingSnapshot(item.documentID)
                }
                let result = try stage(
                    item: item,
                    project: project,
                    consent: request.flatteningConsent,
                    operationRoot: operationRoot
                )
                manifest = replacing(
                    manifest,
                    at: index,
                    with: item.updating(
                        state: .validated,
                        progressCompleted: 3,
                        artifactHash: result.artifactHash,
                        publicationIntent: BatchPublicationIntent(
                            destinationFile: item.destinationFile,
                            expectedArtifactHash: result.artifactHash
                        )
                    )
                )
                try store.persist(manifest, at: operationRoot)
                progress(manifest)
                if cancellation?.isCancelled() == true {
                    try store.cleanupItem(operationRoot, itemID: item.itemID)
                    manifest = cancelRemaining(manifest, startingAt: index)
                    try store.cleanupStaging(operationRoot)
                    manifest = manifest.updating(state: .cancelled, cleanupState: .clean)
                    try store.persist(manifest, at: operationRoot)
                    progress(manifest)
                    return manifest
                }
                try injectBeforePublication(execution.fault)
                let staged = store.itemStagingRoot(operationRoot, itemID: item.itemID)
                    .appendingPathComponent(result.fileName)
                let output = request.destination.appendingPathComponent(item.destinationFile)
                guard !fileManager.fileExists(atPath: output.path) else {
                    throw ExportError.destinationExists(item.destinationFile)
                }
                try fileManager.moveItem(at: staged, to: output)
                try injectAfterPublicationMove(execution.fault)
                try fileManager.removeItem(at: store.itemStagingRoot(operationRoot, itemID: item.itemID))
                manifest = replacing(
                    manifest,
                    at: index,
                    with: manifest.items[index].updating(
                        state: .published,
                        progressCompleted: Self.progressTotal,
                        artifactHash: result.artifactHash
                    )
                )
                publishedCount += 1
            } catch BatchExportError.simulatedCrash {
                throw BatchExportError.simulatedCrash
            } catch BatchExportError.injectedProcessFailure {
                try store.cleanupItem(operationRoot, itemID: item.itemID)
                manifest = failed(manifest, at: index, code: "injected-process-failure", message: "하위 프로세스 실패")
            } catch let error as ExportError {
                try store.cleanupItem(operationRoot, itemID: item.itemID)
                let code = destinationExists(error) ? "destination-exists" : "format-export-failed"
                manifest = failed(manifest, at: index, code: code, message: error.localizedDescription)
            } catch let error as CocoaError {
                try store.cleanupItem(operationRoot, itemID: item.itemID)
                let code = error.code == .fileWriteOutOfSpace ? "disk-full" : "filesystem-failure"
                manifest = failed(manifest, at: index, code: code, message: error.localizedDescription)
            }
            try store.persist(manifest, at: operationRoot)
            progress(manifest)
        }
        try store.cleanupStaging(operationRoot)
        let hasFailure = manifest.items.contains { $0.state == .failed }
        manifest = manifest.updating(
            state: hasFailure ? .completedWithErrors : .completed,
            cleanupState: .clean
        )
        try store.persist(manifest, at: operationRoot)
        progress(manifest)
        return manifest
    }

    func recover(destination: URL, operationID: String) throws -> BatchExportManifest {
        try store.recover(destination: destination, operationID: operationID)
    }

    func recoverInterrupted(destination: URL) throws -> [BatchExportManifest] {
        try store.recoverInterrupted(destination: destination)
    }

    func retry(
        destination: URL,
        previousOperationID: String,
        newOperationID: String,
        cancellation: BatchExportCancellation? = nil,
        progress: (BatchExportManifest) -> Void = { _ in }
    ) throws -> BatchExportManifest {
        try run(
            request: try retryRequest(
                destination: destination,
                previousOperationID: previousOperationID,
                newOperationID: newOperationID
            ),
            cancellation: cancellation,
            progress: progress
        )
    }

    func retryRequest(
        destination: URL,
        previousOperationID: String,
        newOperationID: String
    ) throws -> BatchExportRequest {
        try store.retryRequest(
            destination: destination,
            previousOperationID: previousOperationID,
            newOperationID: newOperationID
        )
    }

    func operationExists(destination: URL, operationID: String) -> Bool {
        store.operationExists(destination: destination, operationID: operationID)
    }

    private func stage(
        item: BatchExportItem,
        project: DocumentProject,
        consent: Set<DocumentFormat>,
        operationRoot: URL
    ) throws -> ExportResult {
        let root = store.itemStagingRoot(operationRoot, itemID: item.itemID)
        let receipt = try DocumentExportEngine(fileManager: fileManager).export(
            project: project,
            request: ExportRequest(
                operationID: "stage-\(item.itemID)",
                destination: root,
                formats: [item.format],
                flatteningConsent: consent
            )
        )
        guard let result = receipt.results.first else {
            throw ExportError.invalidPackage("손실 정책으로 차단된 형식: \(item.format.rawValue)")
        }
        return result
    }
}
