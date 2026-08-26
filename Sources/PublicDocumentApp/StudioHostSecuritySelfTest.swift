import AppKit
import WebKit

struct StudioHostSecuritySelfTestReceipt: Encodable {
    let status: String
    let readAccessRoot: String
    let siblingResourceLoaded: Bool
    let contentRuleListInstalled: Bool
    let networkSubresourceExecuted: Bool
    let allowedNavigationSchemes: [String]
    let blockedNetworkSchemes: [String]
    let escapedFileNavigationBlocked: Bool
}

final class StudioHostSecuritySelfTest: NSObject, WKNavigationDelegate, WKScriptMessageHandler {
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
