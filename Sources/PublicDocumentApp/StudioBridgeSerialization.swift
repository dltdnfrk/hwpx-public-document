import Foundation

extension StudioWindowController {
    func decodeProject(from body: [String: Any]) throws -> DocumentProject {
        guard let payload = body["project"] else {
            throw ProjectStoreError.invalidProject
        }
        let data = try JSONSerialization.data(withJSONObject: payload)
        return try JSONDecoder().decode(DocumentProject.self, from: data)
    }

    func send(project: DocumentProject, event: String) throws {
        try send(encodable: project, event: event)
    }

    func send(enforcement: OfficialRuleEnforcement, event: String) throws {
        let projectData = try JSONEncoder().encode(enforcement.project)
        let projectPayload = try JSONSerialization.jsonObject(with: projectData)
        let stateData = try JSONEncoder().encode(enforcement.state)
        let statePayload = try JSONSerialization.jsonObject(with: stateData)
        send(event: event, payload: [
            "project": projectPayload,
            "officialRuleState": statePayload,
        ])
    }

    func send<T: Encodable>(encodable: T, event: String) throws {
        let data = try JSONEncoder().encode(encodable)
        let payload = try JSONSerialization.jsonObject(with: data)
        send(event: event, payload: ["project": payload])
    }

    func send(settings: AISettingsSnapshot, event: String) throws {
        let data = try JSONEncoder().encode(settings)
        let payload = try JSONSerialization.jsonObject(with: data)
        send(event: event, payload: ["settings": payload])
    }

    func send(event: String, payload: [String: Any]) {
        guard
            let data = try? JSONSerialization.data(withJSONObject: ["event": event, "payload": payload]),
            let json = String(data: data, encoding: .utf8)
        else {
            return
        }
        webView.evaluateJavaScript("window.projectStoreReceive(\(json))")
    }
}
