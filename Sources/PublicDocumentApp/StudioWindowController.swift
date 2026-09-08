import AppKit
import WebKit

final class StudioWindowController: NSWindowController, WKNavigationDelegate {
    let webView: WKWebView
    private let studioResources: StudioResourceLocation
    let projectStore: DocumentProjectStore
    let templateCatalogStore: TemplateCatalogStore
    let aiSettingsStore = AISettingsStore()
    let batchRecoveryRegistry = BatchExportRecoveryRegistry()
    var batchCancellation: BatchExportCancellation?
    var qaReadyEmitted = false

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

    static func bundledCatalogEnvelope() throws -> Data {
        let bundled = Bundle.main.resourceURL?.appendingPathComponent("Templates/catalog-envelope.json")
        let local = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
            .appendingPathComponent("Resources/Templates/catalog-envelope.json")
        let source = bundled.flatMap { FileManager.default.fileExists(atPath: $0.path) ? $0 : nil } ?? local
        return try Data(contentsOf: source)
    }
}
