import AppKit

extension StudioWindowController {
    func chooseCatalogUpdate() throws {
        let panel = NSOpenPanel()
        panel.title = "서명된 템플릿 카탈로그 선택"
        panel.message = "검증된 카탈로그만 설치되며 현재 문서의 고정 템플릿은 변경되지 않습니다."
        panel.allowedContentTypes = [.json]
        panel.allowsMultipleSelection = false
        guard panel.runModal() == .OK, let selected = panel.url else {
            send(event: "templateCatalogCancelled", payload: [:])
            return
        }
        let status = try templateCatalogStore.install(Data(contentsOf: selected))
        try send(encodable: status, event: "templateCatalog")
    }

    func openCanonicalProject(event: String) throws {
        let enforcement = try templateCatalogStore.enforceOfficialRules(
            in: projectStore.loadCanonical()
        )
        if enforcement.state.contentChanged {
            try projectStore.save(enforcement.project)
        }
        try send(enforcement: enforcement, event: event)
    }

    func openRecoveringProject(event: String) throws {
        let loadedFromRecovery = projectStore.hasRecovery()
        let enforcement = try templateCatalogStore.enforceOfficialRules(
            in: projectStore.loadRecoveringAutosave()
        )
        if enforcement.state.contentChanged {
            if loadedFromRecovery {
                try projectStore.autosave(enforcement.project)
            } else {
                try projectStore.save(enforcement.project)
            }
        }
        try send(enforcement: enforcement, event: event)
    }
}
