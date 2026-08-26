import Foundation
import Security

enum AIProviderTransportError: Error, LocalizedError {
    case invalidEndpoint
    case credentialUnavailable
    case invalidResponse
    case responseTooLarge
    case requestFailed(Int)

    var errorDescription: String? {
        switch self {
        case .invalidEndpoint: return "AI 제공자 엔드포인트가 올바르지 않습니다."
        case .credentialUnavailable: return "macOS 키체인에서 제공자 자격 증명을 찾을 수 없습니다."
        case .invalidResponse: return "AI 제공자가 유효한 문서 명령을 반환하지 않았습니다."
        case .responseTooLarge: return "AI 제공자 응답이 허용 크기를 초과했습니다."
        case .requestFailed(let status): return "AI 제공자 요청이 실패했습니다(HTTP \(status))."
        }
    }
}

struct AIKeychainCredentialStore {
    private let service: String

    init(service: String? = nil) {
        self.service = service
            ?? ProcessInfo.processInfo.environment["PUBLIC_DOCUMENT_STUDIO_AI_KEYCHAIN_SERVICE"]
            ?? "com.muni.public-document.ai-provider"
    }

    func set(secret: String, accountReference: String) throws {
        let query: [CFString: Any] = [
            kSecClass: kSecClassGenericPassword,
            kSecAttrService: service,
            kSecAttrAccount: accountReference,
        ]
        let data = Data(secret.utf8)
        let updateStatus = SecItemUpdate(
            query as CFDictionary,
            [kSecValueData: data] as CFDictionary
        )
        if updateStatus == errSecSuccess {
            return
        }
        guard updateStatus == errSecItemNotFound else {
            throw AIProviderTransportError.credentialUnavailable
        }
        var item = query
        item[kSecValueData] = data
        item[kSecAttrAccessible] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        item[kSecAttrSynchronizable] = kCFBooleanFalse as Any
        guard SecItemAdd(item as CFDictionary, nil) == errSecSuccess else {
            throw AIProviderTransportError.credentialUnavailable
        }
    }

    func get(accountReference: String) throws -> String {
        let query: [CFString: Any] = [
            kSecClass: kSecClassGenericPassword,
            kSecAttrService: service,
            kSecAttrAccount: accountReference,
            kSecReturnData: true,
            kSecMatchLimit: kSecMatchLimitOne,
        ]
        var result: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess,
              let data = result as? Data,
              let secret = String(data: data, encoding: .utf8)
        else { throw AIProviderTransportError.credentialUnavailable }
        return secret
    }

    func delete(accountReference: String) throws {
        let query: [CFString: Any] = [
            kSecClass: kSecClassGenericPassword,
            kSecAttrService: service,
            kSecAttrAccount: accountReference,
        ]
        let status = SecItemDelete(query as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else {
            throw AIProviderTransportError.credentialUnavailable
        }
    }
}

struct AIProviderTransport {
    private let session: URLSession

    init() {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.urlCache = nil
        configuration.requestCachePolicy = .reloadIgnoringLocalCacheData
        configuration.timeoutIntervalForRequest = 60
        configuration.timeoutIntervalForResource = 90
        session = URLSession(configuration: configuration)
    }

    func request(
        binding: AIRequestBinding,
        instruction: String,
        elements: [DocumentElement],
        credential: String,
        completion: @escaping (Result<[AIProposalCommand], Error>) -> Void
    ) {
        do {
            let request = try makeRequest(
                binding: binding, instruction: instruction,
                elements: elements, credential: credential
            )
            session.dataTask(with: request) { data, response, error in
                if let error {
                    completion(.failure(error))
                    return
                }
                guard let http = response as? HTTPURLResponse else {
                    completion(.failure(AIProviderTransportError.invalidResponse))
                    return
                }
                guard (200..<300).contains(http.statusCode) else {
                    completion(.failure(AIProviderTransportError.requestFailed(http.statusCode)))
                    return
                }
                guard let data, data.count <= 1_048_576 else {
                    completion(.failure(AIProviderTransportError.responseTooLarge))
                    return
                }
                do {
                    completion(.success(try parseCommands(data, provider: binding.provider)))
                } catch {
                    completion(.failure(error))
                }
            }.resume()
        } catch {
            completion(.failure(error))
        }
    }

    func makeRequest(
        binding: AIRequestBinding,
        instruction: String,
        elements: [DocumentElement],
        credential: String
    ) throws -> URLRequest {
        guard var url = URL(string: binding.endpointIdentity), Self.endpointIsAllowed(url, provider: binding.provider)
        else { throw AIProviderTransportError.invalidEndpoint }
        switch binding.provider {
        case .openAI, .openAICompatible:
            if !url.path.hasSuffix("/chat/completions") { url.append(path: "chat/completions") }
        case .anthropic:
            if url.path == "/v1" {
                url.append(path: "messages")
            } else if !url.path.hasSuffix("/v1/messages") {
                url.append(path: "v1/messages")
            }
        case .gemini:
            if !url.path.contains(":generateContent") {
                url.append(path: "v1beta/models/\(binding.model):generateContent")
            }
        }
        let scopedElements = elements.map { ["elementID": $0.elementID, "text": $0.text] }
        let input = try JSONSerialization.data(withJSONObject: [
            "operation": binding.operation.rawValue,
            "instruction": instruction,
            "payloadScope": binding.payloadScope,
            "elements": scopedElements,
        ])
        let content = String(decoding: input, as: UTF8.self)
        let schemaInstruction = Self.schemaInstruction(for: binding.operation)
        let body: [String: Any]
        var request = URLRequest(url: url)
        switch binding.provider {
        case .openAI, .openAICompatible:
            request.setValue("Bearer \(credential)", forHTTPHeaderField: "Authorization")
            body = ["model": binding.model, "messages": [["role": "system", "content": schemaInstruction], ["role": "user", "content": content]], "response_format": ["type": "json_object"]]
        case .anthropic:
            request.setValue(credential, forHTTPHeaderField: "x-api-key")
            request.setValue("2023-06-01", forHTTPHeaderField: "anthropic-version")
            body = ["model": binding.model, "max_tokens": 4096, "system": schemaInstruction, "messages": [["role": "user", "content": content]]]
        case .gemini:
            request.setValue(credential, forHTTPHeaderField: "x-goog-api-key")
            body = ["system_instruction": ["parts": [["text": schemaInstruction]]], "contents": [["parts": [["text": content]]]]]
        }
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        return request
    }

    static func schemaInstruction(for operation: AIOperation) -> String {
        let command = operation == .missingDataMarking ? "replace-text with value containing [확인 필요]" : operation == .evidenceClaimCheck ? "evidence-check" : operation == .tableChange ? "table-cell-update with targetPath table:<table-id>/<cell-path>" : "replace-text"
        return "Return only JSON: {\"commands\":[{\"commandID\":\"id\",\"name\":\"\(command)\",\"targetElementID\":\"existing-id\",\"targetPath\":\"optional\",\"value\":\"replacement\"}]}"
    }

    func parseCommands(_ data: Data, provider: AIProviderKind) throws -> [AIProposalCommand] {
        guard let root = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw AIProviderTransportError.invalidResponse
        }
        let content: String?
        switch provider {
        case .openAI, .openAICompatible:
            content = ((root["choices"] as? [[String: Any]])?.first?["message"] as? [String: Any])?["content"] as? String
        case .anthropic:
            content = (root["content"] as? [[String: Any]])?.first?["text"] as? String
        case .gemini:
            content = ((((root["candidates"] as? [[String: Any]])?.first?["content"] as? [String: Any])?["parts"] as? [[String: Any]])?.first?["text"] as? String)
        }
        guard let content,
              let jsonStart = content.firstIndex(of: "{"), let jsonEnd = content.lastIndex(of: "}"),
              let payload = String(content[jsonStart...jsonEnd]).data(using: .utf8),
              let envelope = try JSONSerialization.jsonObject(with: payload) as? [String: Any],
              let rawCommands = envelope["commands"] as? [[String: Any]], !rawCommands.isEmpty
        else { throw AIProviderTransportError.invalidResponse }
        return try rawCommands.map { command in
            guard let name = command["name"] as? String,
                  let target = command["targetElementID"] as? String,
                  let value = command["value"] as? String
            else { throw AIProviderTransportError.invalidResponse }
            return AIProposalCommand(
                commandID: command["commandID"] as? String ?? "command-\(UUID().uuidString)",
                name: name, targetElementID: target, value: value,
                targetPath: command["targetPath"] as? String
            )
        }
    }

    static func endpointIsAllowed(_ url: URL, provider: AIProviderKind = .openAICompatible) -> Bool {
        let host = url.host?.lowercased() ?? ""
        switch provider {
        case .openAI, .anthropic, .gemini:
            let policy = AIProviderCatalog.policy(for: provider)
            return url.scheme?.lowercased() == "https" && policy.allowedHosts.contains(host)
        case .openAICompatible:
            if url.scheme?.lowercased() == "https" { return true }
            guard url.scheme?.lowercased() == "http", let host = url.host?.lowercased() else {
                return false
            }
            return host == "localhost" || host == "127.0.0.1" || host == "::1"
        }
    }
}
