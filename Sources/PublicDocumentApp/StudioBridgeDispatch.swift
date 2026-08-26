import WebKit

extension StudioWindowController: WKScriptMessageHandler {
    func userContentController(
        _ userContentController: WKUserContentController,
        didReceive message: WKScriptMessage
    ) {
        guard
            message.name == "projectStore",
            let body = message.body as? [String: Any],
            let action = body["action"] as? String
        else {
            send(event: "error", payload: ["message": "잘못된 프로젝트 요청입니다."])
            return
        }

        do {
            switch action {
            case "ready":
                do {
                    if projectStore.hasRecovery() || projectStore.hasProject() {
                        let project = try projectStore.loadRecoveringAutosave()
                        _ = try aiSettingsStore.migrateLegacyConfigurations(
                            project.providerConfigurations
                        )
                    }
                    try send(settings: aiSettingsStore.snapshot(), event: "aiSettingsLoaded")
                } catch {
                    try send(settings: AISettingsSnapshot.unavailable, event: "aiSettingsLoaded")
                    send(event: "aiSettingsUnavailable", payload: [
                        "message": "AI 설정을 불러오지 못했지만 문서 기능은 계속 사용할 수 있습니다.",
                    ])
                }
                try send(encodable: templateCatalogStore.bootstrap(), event: "templateCatalog")
                recoverKnownBatchExports()
                if projectStore.hasRecovery() {
                    try openRecoveringProject(event: "recovered")
                } else if projectStore.hasProject() {
                    try openCanonicalProject(event: "opened")
                } else {
                    send(event: "empty", payload: [:])
                }
            case "save":
                let enforcement = try templateCatalogStore.enforceOfficialRules(
                    in: decodeProject(from: body)
                )
                try projectStore.save(enforcement.project)
                try send(enforcement: enforcement, event: "saved")
            case "autosave":
                let enforcement = try templateCatalogStore.enforceOfficialRules(
                    in: decodeProject(from: body)
                )
                try projectStore.autosave(enforcement.project)
                try send(enforcement: enforcement, event: "autosaved")
            case "reopen":
                try openCanonicalProject(event: "opened")
            case "recover":
                try openRecoveringProject(event: "recovered")
            case "inspect":
                let project = try projectStore.loadRecoveringAutosave()
                try send(encodable: projectStore.inspect(project), event: "inspection")
            case "requestAIProposal":
                try requestAIProposal(from: body)
            case "loadAISettings":
                try send(settings: aiSettingsStore.snapshot(), event: "aiSettingsLoaded")
            case "configureAISettings":
                try configureAISettings(from: body)
            case "testAISettings":
                try testAISettings(from: body)
            case "deleteAISettings":
                try deleteAISettings(from: body)
            case "revokeAIConsent":
                try revokeAIConsent(from: body)
            case "applyAIProposal":
                try applyAIProposal(from: body)
            case "rejectAIProposal":
                try rejectAIProposal(from: body)
            case "undoAIRevision":
                try send(project: try undoAIRevision(), event: "aiRevisionUndone")
            case "redoAIRevision":
                try send(project: try redoAIRevision(), event: "aiRevisionRedone")
            case "export":
                try chooseExport(from: body)
            case "batchExport":
                try chooseBatchExport(from: body)
            case "cancelBatchExport":
                batchCancellation?.cancel()
                send(event: "batchExportCancelling", payload: [:])
            case "retryBatchExport":
                try retryBatchExport(from: body)
            case "updateTemplateCatalog":
                try chooseCatalogUpdate()
            case "rollbackTemplateCatalog":
                try send(encodable: templateCatalogStore.rollback(), event: "templateCatalog")
            default:
                send(event: "error", payload: ["message": "지원하지 않는 프로젝트 작업입니다."])
            }
        } catch {
            send(event: "error", payload: ["message": error.localizedDescription])
        }
    }
}
