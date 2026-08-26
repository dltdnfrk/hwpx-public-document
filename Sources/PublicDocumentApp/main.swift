import AppKit
import Darwin
import WebKit

private struct StudioResourceLocation {
    let entry: URL
    let readAccessRoot: URL

    init(entry: URL, readAccessRoot: URL) throws {
        let resolvedRoot = readAccessRoot.standardizedFileURL.resolvingSymlinksInPath()
        let resolvedEntry = entry.standardizedFileURL.resolvingSymlinksInPath()
        guard Self.contains(resolvedEntry, within: resolvedRoot) else {
            throw StudioHostSecurityError.resourceOutsideReadAccessRoot
        }
        self.entry = resolvedEntry
        self.readAccessRoot = resolvedRoot
    }

    static func production() throws -> StudioResourceLocation {
        if let bundledRoot = Bundle.main.resourceURL {
            let bundledEntry = bundledRoot.appendingPathComponent("Studio/index.html")
            if FileManager.default.fileExists(atPath: bundledEntry.path) {
                return try StudioResourceLocation(entry: bundledEntry, readAccessRoot: bundledRoot)
            }
        }
        let localRoot = URL(fileURLWithPath: FileManager.default.currentDirectoryPath, isDirectory: true)
            .appendingPathComponent("Resources", isDirectory: true)
        return try StudioResourceLocation(
            entry: localRoot.appendingPathComponent("Studio/index.html"),
            readAccessRoot: localRoot
        )
    }

    func contains(_ candidate: URL) -> Bool {
        Self.contains(candidate.standardizedFileURL.resolvingSymlinksInPath(), within: readAccessRoot)
    }

    private static func contains(_ candidate: URL, within root: URL) -> Bool {
        candidate.path == root.path || candidate.path.hasPrefix(root.path + "/")
    }
}

private enum StudioHostSecurityError: LocalizedError {
    case resourceOutsideReadAccessRoot
    case offlineContentRuleUnavailable
    case hostProbeFailed(String)

    var errorDescription: String? {
        switch self {
        case .resourceOutsideReadAccessRoot:
            return "Studio resource escaped the approved Resources root."
        case .offlineContentRuleUnavailable:
            return "The offline WebKit content rule could not be installed."
        case let .hostProbeFailed(message):
            return "Studio host security probe failed: \(message)"
        }
    }
}

private enum StudioOfflinePolicy {
    static let blockedNetworkSchemes = ["http", "https", "ws", "wss"]
    static let contentRuleIdentifier = "PublicDocumentStudio.OfflineNetworkDeny.v1"
    static let encodedContentRuleList = """
    [
      {
        "trigger": { "url-filter": "^https?://" },
        "action": { "type": "block" }
      },
      {
        "trigger": { "url-filter": "^wss?://" },
        "action": { "type": "block" }
      }
    ]
    """

    static func allowsNavigation(to url: URL?, within resources: StudioResourceLocation) -> Bool {
        guard let url, let scheme = url.scheme?.lowercased() else { return false }
        switch scheme {
        case "about":
            return true
        case "file":
            return resources.contains(url)
        default:
            return false
        }
    }

    static func installContentRule(
        in userContentController: WKUserContentController,
        completion: @escaping (Result<Void, Error>) -> Void
    ) {
        WKContentRuleListStore.default().compileContentRuleList(
            forIdentifier: contentRuleIdentifier,
            encodedContentRuleList: encodedContentRuleList
        ) { contentRuleList, error in
            DispatchQueue.main.async {
                if let error {
                    completion(.failure(error))
                    return
                }
                guard let contentRuleList else {
                    completion(.failure(StudioHostSecurityError.offlineContentRuleUnavailable))
                    return
                }
                userContentController.add(contentRuleList)
                completion(.success(()))
            }
        }
    }
}

final class StudioWindowController: NSWindowController, WKNavigationDelegate, WKScriptMessageHandler {
    private let webView: WKWebView
    private let studioResources: StudioResourceLocation
    private let projectStore: DocumentProjectStore
    private let templateCatalogStore: TemplateCatalogStore
    private let aiSettingsStore = AISettingsStore()
    private let batchRecoveryRegistry = BatchExportRecoveryRegistry()
    private var batchCancellation: BatchExportCancellation?

    static func make() throws -> StudioWindowController {
        let applicationSupport = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        let defaultCatalogRoot = applicationSupport
            .appendingPathComponent("PublicDocumentStudio", isDirectory: true)
            .appendingPathComponent("Templates", isDirectory: true)
        let catalogRoot = ProcessInfo.processInfo.environment["PUBLIC_DOCUMENT_STUDIO_CATALOG_ROOT"]
            .map { URL(fileURLWithPath: $0, isDirectory: true) } ?? defaultCatalogRoot
        let store = try TemplateCatalogStore(
            root: catalogRoot,
            bundledEnvelope: try bundledCatalogEnvelope()
        )
        return try StudioWindowController(templateCatalogStore: store)
    }

    private init(templateCatalogStore: TemplateCatalogStore) throws {
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .nonPersistent()
        configuration.defaultWebpagePreferences.allowsContentJavaScript = true
        configuration.preferences.javaScriptCanOpenWindowsAutomatically = false
        let applicationSupport = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        let defaultProjectRoot = applicationSupport
                .appendingPathComponent("PublicDocumentStudio", isDirectory: true)
                .appendingPathComponent("Documents", isDirectory: true)
                .appendingPathComponent("Current.publicdocument", isDirectory: true)
        let projectRoot = ProcessInfo.processInfo.environment["PUBLIC_DOCUMENT_STUDIO_PROJECT_ROOT"]
            .map { URL(fileURLWithPath: $0, isDirectory: true) } ?? defaultProjectRoot
        studioResources = try StudioResourceLocation.production()
        projectStore = DocumentProjectStore(root: projectRoot)
        self.templateCatalogStore = templateCatalogStore
        webView = WKWebView(frame: .zero, configuration: configuration)

        let window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 1280, height: 820),
            styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView],
            backing: .buffered,
            defer: false
        )
        window.title = "문서작성기"
        window.titlebarAppearsTransparent = true
        window.titleVisibility = .visible
        window.minSize = NSSize(width: 920, height: 640)
        window.contentView = webView
        window.center()
        window.setFrameAutosaveName("PublicDocumentStudioWindow")
        super.init(window: window)

        configuration.userContentController.add(self, name: "projectStore")
        webView.navigationDelegate = self
        webView.setValue(false, forKey: "drawsBackground")
        StudioOfflinePolicy.installContentRule(in: configuration.userContentController) { [weak self] result in
            switch result {
            case .success:
                self?.loadStudio()
            case let .failure(error):
                self?.showOfflinePolicyFailure(error)
            }
        }
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) {
        fatalError("init(coder:) is unavailable")
    }

    deinit {
        webView.configuration.userContentController.removeScriptMessageHandler(forName: "projectStore")
    }

    private func loadStudio() {
        webView.loadFileURL(studioResources.entry, allowingReadAccessTo: studioResources.readAccessRoot)
    }

    private func showOfflinePolicyFailure(_ error: Error) {
        FileHandle.standardError.write(Data("\(error.localizedDescription)\n".utf8))
        webView.loadHTMLString(
            "<main><h1>Studio를 안전하게 열 수 없습니다.</h1><p>오프라인 보안 정책을 준비하지 못했습니다.</p></main>",
            baseURL: nil
        )
    }

    func webView(
        _ webView: WKWebView,
        decidePolicyFor navigationAction: WKNavigationAction,
        decisionHandler: @escaping (WKNavigationActionPolicy) -> Void
    ) {
        decisionHandler(
            StudioOfflinePolicy.allowsNavigation(
                to: navigationAction.request.url,
                within: studioResources
            ) ? .allow : .cancel
        )
    }

    func webView(
        _ webView: WKWebView,
        decidePolicyFor navigationResponse: WKNavigationResponse,
        decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void
    ) {
        decisionHandler(
            StudioOfflinePolicy.allowsNavigation(
                to: navigationResponse.response.url,
                within: studioResources
            ) ? .allow : .cancel
        )
    }

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

    private static func bundledCatalogEnvelope() throws -> Data {
        let bundled = Bundle.main.resourceURL?.appendingPathComponent("Templates/catalog-envelope.json")
        let local = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
            .appendingPathComponent("Resources/Templates/catalog-envelope.json")
        let source = bundled.flatMap { FileManager.default.fileExists(atPath: $0.path) ? $0 : nil } ?? local
        return try Data(contentsOf: source)
    }

    private func chooseExport(from body: [String: Any]) throws {
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

    private func chooseBatchExport(from body: [String: Any]) throws {
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

    private func retryBatchExport(from body: [String: Any]) throws {
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

    private func startBatch(_ request: BatchExportRequest) {
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

    private func batchInputs(_ projects: [DocumentProject]) -> [BatchDocumentInput] {
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

    private func recoverKnownBatchExports() {
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

    private func requestAIProposal(from body: [String: Any]) throws {
        let enforcement = try templateCatalogStore.enforceOfficialRules(
            in: decodeProject(from: body)
        )
        let project = enforcement.project
        guard body["consent"] as? Bool == true else { throw AIGovernanceError.consentRequired }
        let binding = try aiBinding(from: body, project: project)
        let engine = AIGovernanceEngine()
        let governed = engine.grantConsent(binding, in: project)
        try projectStore.save(governed)
        guard let setting = try? aiSettingsStore.setting(for: binding.provider) else {
            try send(enforcement: OfficialRuleEnforcement(
                project: governed,
                state: enforcement.state
            ), event: "aiProviderUnavailable")
            return
        }
        let credential = try aiSettingsStore.credential(for: setting)
        guard let payloadScope = AIPayloadScope(rawValue: binding.payloadScope) else {
            throw AIGovernanceError.consentRequired
        }
        let scopedElements = try AIGovernanceEngine.scopedElements(
            in: governed,
            scope: payloadScope,
            selectedElementIDs: body["selectedElementIDs"] as? [String] ?? []
        )
        AIProviderTransport().request(
            binding: binding,
            instruction: body["instruction"] as? String ?? "",
            elements: scopedElements,
            credential: credential
        ) { [weak self] result in
            DispatchQueue.main.async {
                guard let self else { return }
                do {
                    switch result {
                    case .success(let commands):
                        let latest = try self.projectStore.loadCanonical()
                        let proposed = try engine.propose(
                            binding: binding, commands: commands,
                            allowedTargetElementIDs: Set(scopedElements.map(\.elementID)),
                            baseRevisionID: governed.currentRevisionID, in: latest
                        ).0
                        try self.projectStore.save(proposed)
                        try self.send(enforcement: OfficialRuleEnforcement(
                            project: proposed,
                            state: enforcement.state
                        ), event: "aiProposal")
                    case .failure(let error):
                        self.send(event: "error", payload: ["message": error.localizedDescription])
                    }
                } catch {
                    self.send(event: "error", payload: ["message": error.localizedDescription])
                }
            }
        }
    }

    private func configureAISettings(from body: [String: Any]) throws {
        guard let rawProvider = body["provider"] as? String,
              let provider = AIProviderKind(rawValue: rawProvider),
              let endpoint = body["endpointIdentity"] as? String,
              let model = body["model"] as? String
        else { throw AISettingsError.invalidProvider }
        _ = try aiSettingsStore.save(
            provider: provider,
            endpointIdentity: endpoint,
            model: model,
            secret: body["secret"] as? String
        )
        try send(settings: aiSettingsStore.snapshot(), event: "aiSettingsSaved")
    }

    private func deleteAISettings(from body: [String: Any]) throws {
        guard let rawProvider = body["provider"] as? String,
              let provider = AIProviderKind(rawValue: rawProvider)
        else { throw AISettingsError.invalidProvider }
        try aiSettingsStore.delete(provider: provider)
        try send(settings: aiSettingsStore.snapshot(), event: "aiSettingsDeleted")
    }

    private func testAISettings(from body: [String: Any]) throws {
        guard let rawProvider = body["provider"] as? String,
              let provider = AIProviderKind(rawValue: rawProvider)
        else { throw AISettingsError.invalidProvider }
        let input = try JSONSerialization.data(withJSONObject: [
            "action": "testAISettings",
            "provider": provider.rawValue,
        ])
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            guard let self else { return }
            let output = AIBridgeCLI.run(input: input, settings: self.aiSettingsStore)
            DispatchQueue.main.async {
                guard let response = try? JSONSerialization.jsonObject(with: output) as? [String: Any],
                      let events = response["events"] as? [[String: Any]]
                else {
                    self.send(event: "error", payload: ["message": AIProviderTransportError.invalidResponse.localizedDescription])
                    return
                }
                for entry in events {
                    guard let event = entry["event"] as? String,
                          let payload = entry["payload"] as? [String: Any]
                    else { continue }
                    self.send(event: event, payload: payload)
                }
            }
        }
    }

    private func revokeAIConsent(from body: [String: Any]) throws {
        let enforcement = try templateCatalogStore.enforceOfficialRules(
            in: decodeProject(from: body)
        )
        var project = enforcement.project
        let binding = try aiBinding(from: body, project: project)
        let matchingGrantIDs = project.consentGrants.filter {
            !$0.revoked && $0.documentID == binding.documentID
                && $0.provider == binding.provider.rawValue
                && $0.endpointIdentity == binding.endpointIdentity
                && $0.model == binding.model
                && $0.operation == binding.operation.rawValue
                && $0.payloadScope == binding.payloadScope
        }.map(\.grantID)
        for grantID in matchingGrantIDs {
            project = AIGovernanceEngine().revokeConsent(grantID: grantID, in: project)
        }
        try projectStore.save(project)
        try send(enforcement: OfficialRuleEnforcement(
            project: project,
            state: enforcement.state
        ), event: "aiConsentRevoked")
    }

    private func applyAIProposal(from body: [String: Any]) throws {
        guard let proposalID = body["proposalID"] as? String else {
            throw AIGovernanceError.proposalUnavailable
        }
        let project = try projectStore.loadCanonical()
        let commandIDs = Set(body["commandIDs"] as? [String] ?? [])
        let updated = try AIGovernanceEngine().approve(
            proposalID: proposalID, commandIDs: commandIDs, in: project
        )
        let enforcement = try templateCatalogStore.enforceOfficialRules(in: updated)
        try projectStore.save(enforcement.project)
        try send(enforcement: enforcement, event: "aiProposalApplied")
    }

    private func rejectAIProposal(from body: [String: Any]) throws {
        guard let proposalID = body["proposalID"] as? String else {
            throw AIGovernanceError.proposalUnavailable
        }
        let updated = try AIGovernanceEngine().reject(
            proposalID: proposalID, in: projectStore.loadCanonical()
        )
        let enforcement = try templateCatalogStore.enforceOfficialRules(in: updated)
        try projectStore.save(enforcement.project)
        try send(enforcement: enforcement, event: "aiProposalRejected")
    }

    private func undoAIRevision() throws -> DocumentProject {
        let updated = try AIGovernanceEngine().undo(in: projectStore.loadCanonical())
        try projectStore.save(updated)
        return updated
    }

    private func redoAIRevision() throws -> DocumentProject {
        let updated = try AIGovernanceEngine().redo(in: projectStore.loadCanonical())
        try projectStore.save(updated)
        return updated
    }

    private func aiBinding(from body: [String: Any], project: DocumentProject) throws -> AIRequestBinding {
        guard let rawProvider = body["provider"] as? String,
              let provider = AIProviderKind(rawValue: rawProvider),
              let rawOperation = body["operation"] as? String,
              let operation = AIOperation(rawValue: rawOperation),
              let payloadScope = body["payloadScope"] as? String, !payloadScope.isEmpty
        else { throw AIGovernanceError.consentRequired }
        let setting = try aiSettingsStore.setting(for: provider)
        return AIRequestBinding(
            documentID: project.documentID, provider: provider,
            endpointIdentity: setting.endpointIdentity, model: setting.model,
            operation: operation, payloadScope: payloadScope
        )
    }

    private func chooseCatalogUpdate() throws {
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

    private func openCanonicalProject(event: String) throws {
        let enforcement = try templateCatalogStore.enforceOfficialRules(
            in: projectStore.loadCanonical()
        )
        if enforcement.state.contentChanged {
            try projectStore.save(enforcement.project)
        }
        try send(enforcement: enforcement, event: event)
    }

    private func openRecoveringProject(event: String) throws {
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

    private func decodeProject(from body: [String: Any]) throws -> DocumentProject {
        guard let payload = body["project"] else {
            throw ProjectStoreError.invalidProject
        }
        let data = try JSONSerialization.data(withJSONObject: payload)
        return try JSONDecoder().decode(DocumentProject.self, from: data)
    }

    private func send(project: DocumentProject, event: String) throws {
        try send(encodable: project, event: event)
    }

    private func send(enforcement: OfficialRuleEnforcement, event: String) throws {
        let projectData = try JSONEncoder().encode(enforcement.project)
        let projectPayload = try JSONSerialization.jsonObject(with: projectData)
        let stateData = try JSONEncoder().encode(enforcement.state)
        let statePayload = try JSONSerialization.jsonObject(with: stateData)
        send(event: event, payload: [
            "project": projectPayload,
            "officialRuleState": statePayload,
        ])
    }

    private func send<T: Encodable>(encodable: T, event: String) throws {
        let data = try JSONEncoder().encode(encodable)
        let payload = try JSONSerialization.jsonObject(with: data)
        send(event: event, payload: ["project": payload])
    }

    private func send(settings: AISettingsSnapshot, event: String) throws {
        let data = try JSONEncoder().encode(settings)
        let payload = try JSONSerialization.jsonObject(with: data)
        send(event: event, payload: ["settings": payload])
    }

    private func send(event: String, payload: [String: Any]) {
        guard
            let data = try? JSONSerialization.data(withJSONObject: ["event": event, "payload": payload]),
            let json = String(data: data, encoding: .utf8)
        else {
            return
        }
        webView.evaluateJavaScript("window.projectStoreReceive(\(json))")
    }
}

private struct StudioHostSecuritySelfTestReceipt: Encodable {
    let status: String
    let readAccessRoot: String
    let siblingResourceLoaded: Bool
    let contentRuleListInstalled: Bool
    let networkSubresourceExecuted: Bool
    let allowedNavigationSchemes: [String]
    let blockedNetworkSchemes: [String]
    let escapedFileNavigationBlocked: Bool
}

private final class StudioHostSecuritySelfTest: NSObject, WKNavigationDelegate, WKScriptMessageHandler {
    private let resources: StudioResourceLocation
    private var webView: WKWebView?
    private var contentRuleListInstalled = false
    private var siblingResourceLoaded: Bool?
    private var networkSubresourceExecuted: Bool?
    private var failure: Error?

    init(resourcesRoot: URL) throws {
        resources = try StudioResourceLocation(
            entry: resourcesRoot.appendingPathComponent("Studio/index.html"),
            readAccessRoot: resourcesRoot
        )
        super.init()
    }

    func run() throws -> StudioHostSecuritySelfTestReceipt {
        guard FileManager.default.fileExists(atPath: resources.entry.path) else {
            throw StudioHostSecurityError.hostProbeFailed("missing Studio/index.html")
        }
        let siblingRuntime = resources.readAccessRoot
            .appendingPathComponent("GenOffice/public-document-genoffice.js")
        guard FileManager.default.fileExists(atPath: siblingRuntime.path) else {
            throw StudioHostSecurityError.hostProbeFailed("missing GenOffice sibling runtime")
        }

        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .nonPersistent()
        configuration.defaultWebpagePreferences.allowsContentJavaScript = true
        configuration.preferences.javaScriptCanOpenWindowsAutomatically = false
        configuration.userContentController.add(self, name: "hostSecurityProbe")
        let probeWebView = WKWebView(frame: NSRect(x: 0, y: 0, width: 800, height: 600), configuration: configuration)
        probeWebView.navigationDelegate = self
        webView = probeWebView

        StudioOfflinePolicy.installContentRule(in: configuration.userContentController) { [weak self] result in
            guard let self else { return }
            switch result {
            case .success:
                self.contentRuleListInstalled = true
                self.webView?.loadFileURL(
                    self.resources.entry,
                    allowingReadAccessTo: self.resources.readAccessRoot
                )
            case let .failure(error):
                self.failure = error
            }
        }

        let deadline = Date().addingTimeInterval(15)
        while siblingResourceLoaded == nil, failure == nil, Date() < deadline {
            RunLoop.main.run(mode: .default, before: Date().addingTimeInterval(0.05))
        }

        configuration.userContentController.removeScriptMessageHandler(forName: "hostSecurityProbe")
        probeWebView.stopLoading()
        probeWebView.navigationDelegate = nil
        webView = nil

        if let failure { throw failure }
        guard siblingResourceLoaded == true else {
            throw StudioHostSecurityError.hostProbeFailed("GenOffice sibling runtime was not ready")
        }
        guard networkSubresourceExecuted == false else {
            throw StudioHostSecurityError.hostProbeFailed("an HTTP subresource executed")
        }

        let allowedNavigationSchemes = ["file", "about"].filter { scheme in
            let candidate = scheme == "file" ? resources.entry : URL(string: "about:blank")!
            return StudioOfflinePolicy.allowsNavigation(to: candidate, within: resources)
        }
        let blockedNetworkSchemes = StudioOfflinePolicy.blockedNetworkSchemes.filter { scheme in
            !StudioOfflinePolicy.allowsNavigation(
                to: URL(string: "\(scheme)://127.0.0.1/probe"),
                within: resources
            )
        }
        let escapedFile = resources.readAccessRoot.deletingLastPathComponent()
            .appendingPathComponent("outside.html")
        let escapedFileNavigationBlocked = !StudioOfflinePolicy.allowsNavigation(
            to: escapedFile,
            within: resources
        )
        guard contentRuleListInstalled,
              allowedNavigationSchemes == ["file", "about"],
              blockedNetworkSchemes == StudioOfflinePolicy.blockedNetworkSchemes,
              escapedFileNavigationBlocked
        else {
            throw StudioHostSecurityError.hostProbeFailed("native policy assertions failed")
        }

        return StudioHostSecuritySelfTestReceipt(
            status: "PASS",
            readAccessRoot: resources.readAccessRoot.path,
            siblingResourceLoaded: true,
            contentRuleListInstalled: true,
            networkSubresourceExecuted: false,
            allowedNavigationSchemes: allowedNavigationSchemes,
            blockedNetworkSchemes: blockedNetworkSchemes,
            escapedFileNavigationBlocked: escapedFileNavigationBlocked
        )
    }

    func webView(
        _ webView: WKWebView,
        decidePolicyFor navigationAction: WKNavigationAction,
        decisionHandler: @escaping (WKNavigationActionPolicy) -> Void
    ) {
        decisionHandler(
            StudioOfflinePolicy.allowsNavigation(
                to: navigationAction.request.url,
                within: resources
            ) ? .allow : .cancel
        )
    }

    func webView(
        _ webView: WKWebView,
        decidePolicyFor navigationResponse: WKNavigationResponse,
        decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void
    ) {
        decisionHandler(
            StudioOfflinePolicy.allowsNavigation(
                to: navigationResponse.response.url,
                within: resources
            ) ? .allow : .cancel
        )
    }

    func webView(
        _ webView: WKWebView,
        didFailProvisionalNavigation navigation: WKNavigation!,
        withError error: Error
    ) {
        failure = error
    }

    func webView(
        _ webView: WKWebView,
        didFail navigation: WKNavigation!,
        withError error: Error
    ) {
        failure = error
    }

    func userContentController(
        _ userContentController: WKUserContentController,
        didReceive message: WKScriptMessage
    ) {
        guard message.name == "hostSecurityProbe",
              let body = message.body as? [String: Any],
              let siblingReady = body["siblingReady"] as? Bool,
              let networkExecuted = body["networkExecuted"] as? Bool
        else {
            failure = StudioHostSecurityError.hostProbeFailed("invalid JavaScript readiness message")
            return
        }
        siblingResourceLoaded = siblingReady
        networkSubresourceExecuted = networkExecuted
    }
}

final class PublicDocumentStudioApp: NSObject, NSApplicationDelegate {
    private var studioWindowController: StudioWindowController?

    static func run() {
        let arguments = CommandLine.arguments
        if arguments.count == 2, arguments[1] == "--ai-bridge-stdin" {
            let input = FileHandle.standardInput.readDataToEndOfFile()
            FileHandle.standardOutput.write(AIBridgeCLI.run(input: input))
            FileHandle.standardOutput.write(Data("\n".utf8))
            return
        }
        if arguments.count == 3, arguments[1] == "--ai-settings-self-test" {
            do {
                let receipt = try AISettingsSelfTest.run(
                    at: URL(fileURLWithPath: arguments[2], isDirectory: true)
                )
                try ProjectSelfTest.printJSON(receipt)
                return
            } catch {
                FileHandle.standardError.write(Data("\(error.localizedDescription)\n".utf8))
                Darwin.exit(EXIT_FAILURE)
            }
        }
        if arguments.count == 3, arguments[1] == "--studio-host-security-self-test" {
            do {
                let application = NSApplication.shared
                application.setActivationPolicy(.prohibited)
                application.finishLaunching()
                let receipt = try StudioHostSecuritySelfTest(
                    resourcesRoot: URL(fileURLWithPath: arguments[2], isDirectory: true)
                ).run()
                try ProjectSelfTest.printJSON(receipt)
                return
            } catch {
                FileHandle.standardError.write(Data("\(error.localizedDescription)\n".utf8))
                Darwin.exit(EXIT_FAILURE)
            }
        }
        if arguments.count == 3, arguments[1] == "--ai-governance-self-test" {
            do {
                let receipt = try AIGovernanceSelfTest.run(at: URL(fileURLWithPath: arguments[2]))
                try ProjectSelfTest.printJSON(receipt)
                return
            } catch {
                FileHandle.standardError.write(Data("\(error)\n".utf8))
                Darwin.exit(EXIT_FAILURE)
            }
        }
        if arguments.count == 3, arguments[1] == "--template-catalog-self-test" {
            do {
                let receipt = try TemplateCatalogSelfTest.run(at: URL(fileURLWithPath: arguments[2]))
                try ProjectSelfTest.printJSON(receipt)
                return
            } catch {
                FileHandle.standardError.write(Data("\(error)\n".utf8))
                Darwin.exit(EXIT_FAILURE)
            }
        }
        if arguments.count == 3, arguments[1] == "--export-official-samples" {
            do {
                try OfficialStyleSamples.export(to: URL(fileURLWithPath: arguments[2], isDirectory: true))
                return
            } catch {
                FileHandle.standardError.write(Data("\(error)\n".utf8))
                Darwin.exit(EXIT_FAILURE)
            }
        }
        if arguments.count >= 4, arguments[1] == "--export-project" {
            do {
                let project = try JSONDecoder().decode(
                    DocumentProject.self,
                    from: Data(contentsOf: URL(fileURLWithPath: arguments[2]))
                )
                var formats: [DocumentFormat] = [.docx, .hwpx]
                var consent = false
                var index = 4
                while index < arguments.count {
                    if arguments[index] == "--formats", index + 1 < arguments.count {
                        formats = arguments[index + 1]
                            .split(separator: ",")
                            .compactMap { DocumentFormat(rawValue: String($0)) }
                        index += 2
                    } else if arguments[index] == "--flattening-consent" {
                        consent = true
                        index += 1
                    } else {
                        index += 1
                    }
                }
                guard !formats.isEmpty else { throw ExportError.noFormatSelected }
                let receipt = try DocumentExportEngine().export(
                    project: project,
                    request: ExportRequest(
                        operationID: "web-export-\(UUID().uuidString)",
                        destination: URL(fileURLWithPath: arguments[3], isDirectory: true),
                        formats: formats,
                        flatteningConsent: consent ? Set(formats) : []
                    )
                )
                try ProjectSelfTest.printJSON(receipt)
                Darwin.exit(EXIT_SUCCESS)
            } catch {
                FileHandle.standardError.write(Data("\(error)\n".utf8))
                Darwin.exit(EXIT_FAILURE)
            }
        }
        if arguments.count == 3, arguments[1] == "--verify-template-catalog-envelope" {
            do {
                let envelope = try Data(contentsOf: URL(fileURLWithPath: arguments[2]))
                let store = try TemplateCatalogStore(
                    root: FileManager.default.temporaryDirectory,
                    bundledEnvelope: envelope
                )
                try ProjectSelfTest.printJSON(store.verifiedCatalog(from: envelope))
                return
            } catch {
                FileHandle.standardError.write(Data("\(error)\n".utf8))
                Darwin.exit(EXIT_FAILURE)
            }
        }
        if arguments.count == 3, arguments[1] == "--project-store-self-test" {
            do {
                let receipt = try ProjectSelfTest.runLifecycle(at: URL(fileURLWithPath: arguments[2]))
                try ProjectSelfTest.printJSON(receipt)
                return
            } catch {
                FileHandle.standardError.write(Data("\(error)\n".utf8))
                Darwin.exit(EXIT_FAILURE)
            }
        }
        if arguments.count == 3, arguments[1] == "--project-migration-self-test" {
            do {
                let receipt = try ProjectSelfTest.runMigration(at: URL(fileURLWithPath: arguments[2]))
                try ProjectSelfTest.printJSON(receipt)
                return
            } catch {
                FileHandle.standardError.write(Data("\(error)\n".utf8))
                Darwin.exit(EXIT_FAILURE)
            }
        }
        if arguments.count == 4, arguments[1] == "--export-self-test" {
            do {
                guard let scenario = ExportSelfTestScenario(rawValue: arguments[3]) else {
                    throw ExportError.invalidPackage("알 수 없는 내보내기 자체 시험")
                }
                let receipt = try ExportSelfTest.run(
                    at: URL(fileURLWithPath: arguments[2], isDirectory: true),
                    scenario: scenario
                )
                try ProjectSelfTest.printJSON(receipt)
                return
            } catch {
                FileHandle.standardError.write(Data("\(error)\n".utf8))
                Darwin.exit(EXIT_FAILURE)
            }
        }
        if arguments.count == 4, arguments[1] == "--batch-export-self-test" {
            do {
                guard let scenario = BatchExportSelfTestScenario(rawValue: arguments[3]) else {
                    throw ExportError.invalidPackage("알 수 없는 배치 내보내기 자체 시험")
                }
                let root = URL(fileURLWithPath: arguments[2], isDirectory: true)
                switch scenario {
                case .partialFailure, .cancelAfterFirst, .cancelBeforePublication, .existingDestination:
                    try ProjectSelfTest.printJSON(BatchExportSelfTest.run(at: root, scenario: scenario))
                case .crashAndRetry, .diskFullAndRetry:
                    try ProjectSelfTest.printJSON(BatchExportSelfTest.runRecovery(at: root, scenario: scenario))
                }
                return
            } catch {
                FileHandle.standardError.write(Data("\(error)\n".utf8))
                Darwin.exit(EXIT_FAILURE)
            }
        }
        if arguments.count == 3, arguments[1] == "--compatibility-self-test" {
            do {
                let receipt = try CompatibilitySelfTest.run(
                    at: URL(fileURLWithPath: arguments[2], isDirectory: true)
                )
                try ProjectSelfTest.printJSON(receipt)
                return
            } catch {
                FileHandle.standardError.write(Data("\(error.localizedDescription)\n".utf8))
                Darwin.exit(EXIT_FAILURE)
            }
        }
        if arguments.count == 3, arguments[1] == "--performance-self-test" {
            do {
                let receipt = try PerformanceSelfTest.run(
                    at: URL(fileURLWithPath: arguments[2], isDirectory: true)
                )
                try ProjectSelfTest.printJSON(receipt)
                return
            } catch {
                FileHandle.standardError.write(Data("\(error.localizedDescription)\n".utf8))
                Darwin.exit(EXIT_FAILURE)
            }
        }
        if arguments.count == 4, arguments[1] == "--verify-compatibility-observations" {
            do {
                let receipt = try CompatibilitySelfTest.verify(
                    receipt: URL(fileURLWithPath: arguments[2]),
                    observations: URL(fileURLWithPath: arguments[3])
                )
                try ProjectSelfTest.printJSON(receipt)
                return
            } catch {
                FileHandle.standardError.write(Data("\(error.localizedDescription)\n".utf8))
                Darwin.exit(EXIT_FAILURE)
            }
        }
        let application = NSApplication.shared
        let delegate = PublicDocumentStudioApp()
        application.delegate = delegate
        application.setActivationPolicy(.regular)
        application.finishLaunching()
        if arguments.count == 2, arguments[1] == "--window-lifecycle-self-test" {
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
                let receipt = WindowLifecycleSelfTestReceipt(
                    visibleWindowCount: application.windows.filter(\.isVisible).count
                )
                try? ProjectSelfTest.printJSON(receipt)
                application.terminate(nil)
            }
        }
        application.run()
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        do {
            let controller = try StudioWindowController.make()
            studioWindowController = controller
            controller.showWindow(nil)
            NSApplication.shared.activate(ignoringOtherApps: true)
        } catch {
            FileHandle.standardError.write(Data("\(error.localizedDescription)\n".utf8))
            NSApplication.shared.terminate(nil)
        }
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        true
    }
}

PublicDocumentStudioApp.run()
