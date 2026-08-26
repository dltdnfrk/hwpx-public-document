import AppKit

extension StudioWindowController {
    func chooseExport(from body: [String: Any]) throws {
        let enforcement = try templateCatalogStore.enforceOfficialRules(
            in: decodeProject(from: body)
        )
        let project = enforcement.project
        try projectStore.save(project)
        try send(enforcement: enforcement, event: "officialRuleEnforced")
        let rawFormats = body["formats"] as? [String] ?? []
        let formats = rawFormats.compactMap { DocumentFormat(rawValue: $0) }
        let consent: Set<DocumentFormat> = body["flatteningConsent"] as? Bool == true
            ? Set(formats)
            : []
        let panel = NSOpenPanel()
        panel.title = "내보내기 폴더 선택"
        panel.message = "검증을 통과한 선택 형식만 새 파일로 게시합니다. 기존 파일은 덮어쓰지 않습니다."
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.canCreateDirectories = true
        panel.allowsMultipleSelection = false
        guard panel.runModal() == .OK, let destination = panel.url else {
            send(event: "exportCancelled", payload: [:])
            return
        }
        let receipt = try DocumentExportEngine().export(
            project: project,
            request: ExportRequest(
                operationID: "export-\(UUID().uuidString)",
                destination: destination,
                formats: formats,
                flatteningConsent: consent
            )
        )
        try send(encodable: receipt, event: "exportCompleted")
    }

    func chooseBatchExport(from body: [String: Any]) throws {
        guard batchCancellation == nil else {
            throw ExportError.invalidPackage("진행 중인 일괄 내보내기를 먼저 완료하거나 취소하세요.")
        }
        let enforcement = try templateCatalogStore.enforceOfficialRules(
            in: decodeProject(from: body)
        )
        let current = enforcement.project
        try projectStore.save(current)
        try send(enforcement: enforcement, event: "officialRuleEnforced")
        let sourcePanel = NSOpenPanel()
        sourcePanel.title = "일괄 내보낼 프로젝트 선택"
        sourcePanel.message = "현재 문서와 함께 내보낼 .publicdocument 프로젝트 폴더를 선택하세요."
        sourcePanel.canChooseDirectories = true
        sourcePanel.canChooseFiles = false
        sourcePanel.allowsMultipleSelection = true
        guard sourcePanel.runModal() == .OK else {
            send(event: "batchExportCancelled", payload: [:])
            return
        }

        var projects = [current]
        var documentIDs = Set([current.documentID])
        for source in sourcePanel.urls {
            let loaded = try DocumentProjectStore(root: source).loadRecoveringAutosave()
            let project = try templateCatalogStore.enforceOfficialRules(in: loaded).project
            if documentIDs.insert(project.documentID).inserted { projects.append(project) }
        }
        guard projects.count > 1 else {
            throw ExportError.invalidPackage("서로 다른 프로젝트를 하나 이상 추가로 선택하세요.")
        }
        let destinationPanel = NSOpenPanel()
        destinationPanel.title = "일괄 내보내기 폴더 선택"
        destinationPanel.message = "검증된 문서별 형식만 게시하며 기존 파일은 덮어쓰지 않습니다."
        destinationPanel.canChooseDirectories = true
        destinationPanel.canChooseFiles = false
        destinationPanel.canCreateDirectories = true
        guard destinationPanel.runModal() == .OK, let destination = destinationPanel.url else {
            send(event: "batchExportCancelled", payload: [:])
            return
        }
        let formats = (body["formats"] as? [String] ?? []).compactMap(DocumentFormat.init(rawValue:))
        let consent = body["flatteningConsent"] as? Bool == true ? Set(formats) : []
        let operationID = "batch-\(UUID().uuidString)"
        let documents = batchInputs(projects)
        let request = BatchExportRequest(
            operationID: operationID,
            retryOfOperationID: nil,
            destination: destination,
            documents: documents,
            formats: formats,
            flatteningConsent: consent
        )
        startBatch(request)
    }

    func retryBatchExport(from body: [String: Any]) throws {
        guard batchCancellation == nil else {
            throw ExportError.invalidPackage("진행 중인 일괄 내보내기를 먼저 완료하거나 취소하세요.")
        }
        guard let previousOperationID = body["operationID"] as? String else {
            throw ExportError.invalidPackage("다시 시도할 작업 ID가 없습니다.")
        }
        let coordinator = BatchExportCoordinator()
        guard let destination = batchRecoveryRegistry.destinations().first(where: {
            coordinator.operationExists(destination: $0, operationID: previousOperationID)
        }) else {
            throw ExportError.invalidPackage("다시 시도할 작업 매니페스트를 찾을 수 없습니다.")
        }
        let request = try coordinator.retryRequest(
            destination: destination,
            previousOperationID: previousOperationID,
            newOperationID: "batch-\(UUID().uuidString)"
        )
        let governedDocuments = try request.documents.map { document in
            BatchDocumentInput(
                project: try templateCatalogStore.enforceOfficialRules(in: document.project).project,
                fileStem: document.fileStem
            )
        }
        startBatch(BatchExportRequest(
            operationID: request.operationID,
            retryOfOperationID: request.retryOfOperationID,
            destination: request.destination,
            documents: governedDocuments,
            formats: request.formats,
            flatteningConsent: request.flatteningConsent
        ))
    }

    func startBatch(_ request: BatchExportRequest) {
        let cancellation = BatchExportCancellation()
        batchCancellation = cancellation
        batchRecoveryRegistry.remember(request.destination)
        send(event: "batchExportStarted", payload: ["operationID": request.operationID])
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            do {
                let manifest = try BatchExportCoordinator().run(
                    request: request,
                    cancellation: cancellation
                ) { progress in
                    DispatchQueue.main.async { [weak self] in
                        try? self?.send(encodable: progress, event: "batchExportProgress")
                    }
                }
                DispatchQueue.main.async { [weak self] in
                    self?.batchCancellation = nil
                    try? self?.send(encodable: manifest, event: "batchExportCompleted")
                }
            } catch {
                DispatchQueue.main.async { [weak self] in
                    self?.batchCancellation = nil
                    self?.send(event: "batchExportFailed", payload: [
                        "message": error.localizedDescription,
                    ])
                    self?.send(event: "error", payload: ["message": error.localizedDescription])
                }
            }
        }
    }

    func batchInputs(_ projects: [DocumentProject]) -> [BatchDocumentInput] {
        var usedNames: Set<String> = []
        return projects.map { project in
            let cleaned = String(project.title.map { character in
                "/:\0".contains(character) ? "-" : character
            }).trimmingCharacters(in: .whitespacesAndNewlines)
            let base = cleaned.isEmpty ? project.documentID : cleaned
            let stem = usedNames.insert(base).inserted ? base : "\(base)-\(project.documentID.prefix(8))"
            return BatchDocumentInput(project: project, fileStem: stem)
        }
    }

    func recoverKnownBatchExports() {
        for destination in batchRecoveryRegistry.destinations() {
            do {
                for manifest in try BatchExportCoordinator().recoverInterrupted(destination: destination) {
                    try send(encodable: manifest, event: "batchExportRecovered")
                }
            } catch {
                send(event: "error", payload: [
                    "message": "중단된 일괄 내보내기 복구 실패: \(error.localizedDescription)",
                ])
            }
        }
    }
}
