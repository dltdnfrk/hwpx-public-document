import CryptoKit
import Foundation

final class BatchExportStore {
    static let progressTotal = 4
    static let stateDirectoryName = ".public-document-studio-exports"
    let fileManager: FileManager
    let encoder: JSONEncoder
    let decoder: JSONDecoder

    init(fileManager: FileManager) {
        self.fileManager = fileManager
        encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        decoder = JSONDecoder()
    }

    func prepare(_ operationRoot: URL) throws {
        try fileManager.createDirectory(at: operationRoot, withIntermediateDirectories: true)
        try fileManager.createDirectory(at: snapshotsRoot(operationRoot), withIntermediateDirectories: true)
        try fileManager.createDirectory(at: stagingRoot(operationRoot), withIntermediateDirectories: true)
    }

    func initialManifest(
        request: BatchExportRequest,
        operationRoot: URL,
        selectedFormats: [DocumentFormat]
    ) throws -> BatchExportManifest {
        let documentIDs = request.documents.map { $0.project.documentID }
        guard Set(documentIDs).count == documentIDs.count else {
            throw BatchExportError.missingSnapshot("중복 문서 ID")
        }
        // IDs are embedded in both snapshot filenames and staging directory names.
        // Validate the entire request before writing its first snapshot.
        try documentIDs.forEach(validateDocumentID)
        var items: [BatchExportItem] = []
        for document in request.documents {
            guard !document.fileStem.isEmpty,
                  !document.fileStem.contains("/"),
                  document.fileStem != ".",
                  document.fileStem != ".."
            else { throw BatchExportError.invalidFileStem(document.fileStem) }
            let snapshotData = try encoder.encode(document.project)
            let snapshot = snapshotsRoot(operationRoot)
                .appendingPathComponent("\(document.project.documentID).json")
            try snapshotData.write(to: snapshot, options: .atomic)
            let snapshotHash = "sha256:" + SHA256.hash(data: snapshotData)
                .map { String(format: "%02x", $0) }
                .joined()
            for format in selectedFormats {
                items.append(BatchExportItem(
                    itemID: "\(document.project.documentID)-\(format.rawValue)",
                    documentID: document.project.documentID,
                    documentDisplayName: document.project.title.isEmpty
                        ? document.project.documentID
                        : document.project.title,
                    snapshotRevisionID: document.project.currentRevisionID,
                    snapshotHash: snapshotHash,
                    format: format,
                    destinationFile: "\(document.fileStem).\(format.fileExtension)",
                    state: .queued,
                    progressCompleted: 1,
                    progressTotal: Self.progressTotal,
                    artifactHash: nil,
                    publicationIntent: nil,
                    diagnosticCode: "",
                    diagnosticMessage: ""
                ))
            }
        }
        return BatchExportManifest(
            schemaVersion: 2,
            operationID: request.operationID,
            retryOfOperationID: request.retryOfOperationID,
            state: .running,
            cleanupState: .pending,
            manifestPath: manifestURL(operationRoot).path,
            selectedFormats: selectedFormats,
            flatteningConsent: DocumentFormat.allCases.filter(request.flatteningConsent.contains),
            items: items
        )
    }

    func retryRequest(
        destination: URL,
        previousOperationID: String,
        newOperationID: String
    ) throws -> BatchExportRequest {
        let previousRoot = operationRoot(for: destination, operationID: previousOperationID)
        let manifest = try decoder.decode(
            BatchExportManifest.self,
            from: Data(contentsOf: manifestURL(previousRoot))
        )
        var seenDocumentIDs: Set<String> = []
        var documents: [BatchDocumentInput] = []
        for item in manifest.items where seenDocumentIDs.insert(item.documentID).inserted {
            try validateDocumentID(item.documentID)
            let project = try decoder.decode(
                DocumentProject.self,
                from: Data(contentsOf: snapshotsRoot(previousRoot)
                    .appendingPathComponent("\(item.documentID).json"))
            )
            let suffix = ".\(item.format.fileExtension)"
            guard item.destinationFile.hasSuffix(suffix) else {
                throw BatchExportError.invalidFileStem(item.destinationFile)
            }
            let stem = String(item.destinationFile.dropLast(suffix.count))
            documents.append(BatchDocumentInput(project: project, fileStem: stem))
        }
        return BatchExportRequest(
            operationID: newOperationID,
            retryOfOperationID: previousOperationID,
            destination: destination,
            documents: documents,
            formats: manifest.selectedFormats,
            flatteningConsent: []
        )
    }

    private func validateDocumentID(_ documentID: String) throws {
        guard !documentID.isEmpty,
              documentID != ".", documentID != "..",
              !documentID.contains("/"), !documentID.contains("\\"),
              !documentID.unicodeScalars.contains(where: { CharacterSet.controlCharacters.contains($0) })
        else { throw BatchExportError.invalidFileStem(documentID) }
    }

    func operationExists(destination: URL, operationID: String) -> Bool {
        fileManager.fileExists(atPath: operationRoot(
            for: destination,
            operationID: operationID
        ).path)
    }

    func persist(_ manifest: BatchExportManifest, at operationRoot: URL) throws {
        try encoder.encode(manifest).write(to: manifestURL(operationRoot), options: .atomic)
    }

    func cleanupItem(_ operationRoot: URL, itemID: String) throws {
        let root = itemStagingRoot(operationRoot, itemID: itemID)
        if fileManager.fileExists(atPath: root.path) { try fileManager.removeItem(at: root) }
    }

    func cleanupStaging(_ operationRoot: URL) throws {
        let root = stagingRoot(operationRoot)
        if fileManager.fileExists(atPath: root.path) { try fileManager.removeItem(at: root) }
    }

    func operationRoot(for destination: URL, operationID: String) -> URL {
        destination.appendingPathComponent(Self.stateDirectoryName, isDirectory: true)
            .appendingPathComponent(operationID, isDirectory: true)
    }

    func itemStagingRoot(_ operationRoot: URL, itemID: String) -> URL {
        stagingRoot(operationRoot).appendingPathComponent(itemID, isDirectory: true)
    }

    func snapshotsRoot(_ operationRoot: URL) -> URL {
        operationRoot.appendingPathComponent("snapshots", isDirectory: true)
    }

    func stagingRoot(_ operationRoot: URL) -> URL {
        operationRoot.appendingPathComponent("staging", isDirectory: true)
    }

    func manifestURL(_ operationRoot: URL) -> URL {
        operationRoot.appendingPathComponent("manifest.json")
    }
}
