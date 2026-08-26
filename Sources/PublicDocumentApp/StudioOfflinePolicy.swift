import WebKit

struct StudioResourceLocation {
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

enum StudioHostSecurityError: LocalizedError {
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

enum StudioOfflinePolicy {
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
