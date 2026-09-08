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
        let script = """
        window.projectStoreReceive(\(json));
        JSON.stringify({
          documentTitle: document.title,
          bodyText: String(document.body?.innerText || "").slice(0, 2000),
          projectTitle: globalThis.PublicDocumentStudio?.state?.currentProject?.title || null,
          editorPresent: Boolean(document.querySelector("public-document-genoffice-editor")),
          exportControlPresent: Boolean(document.querySelector('[data-action="export"]')),
          templateControlPresent: Boolean(document.querySelector('[data-template-id]'))
        })
        """
        webView.evaluateJavaScript(script) { [weak self] result, error in
            self?.emitQAReadyIfNeeded(
                event: event,
                payload: payload,
                surfaceJSON: result as? String,
                evaluationError: error
            )
        }
    }

    private func emitQAReadyIfNeeded(
        event: String,
        payload: [String: Any],
        surfaceJSON: String?,
        evaluationError: Error?
    ) {
        guard !qaReadyEmitted,
              let scenario = ProcessInfo.processInfo.environment[
                "PUBLIC_DOCUMENT_STUDIO_QA_SCENARIO"
              ],
              (scenario == "happy"
                && ["opened", "recovered", "empty", "error"].contains(event))
                || (scenario == "invalid-project" && event == "error")
        else {
            return
        }
        qaReadyEmitted = true
        let surface = surfaceJSON
            .flatMap { $0.data(using: .utf8) }
            .flatMap { try? JSONSerialization.jsonObject(with: $0) } as? [String: Any]
        var receipt: [String: Any] = [
            "schemaVersion": 1,
            "scenario": scenario,
            "event": event,
            "windowNumber": window?.windowNumber ?? 0,
            "windowTitle": window?.title ?? "",
            "windowVisible": window?.isVisible ?? false,
            "surface": surface ?? [:],
        ]
        if let diagnostic = payload["message"] as? String {
            receipt["diagnostic"] = diagnostic
        }
        if let evaluationError {
            receipt["evaluationError"] = evaluationError.localizedDescription
        }
        guard let data = try? JSONSerialization.data(
            withJSONObject: receipt,
            options: [.sortedKeys]
        ) else {
            return
        }
        FileHandle.standardOutput.write(Data("PUBLIC_DOCUMENT_STUDIO_QA_READY ".utf8))
        FileHandle.standardOutput.write(data)
        FileHandle.standardOutput.write(Data("\n".utf8))
    }
}
