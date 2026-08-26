import Foundation

extension AIGovernanceSelfTest {
    static func verifyProviderTransport(binding: AIRequestBinding) throws -> (secure: Bool, brandedAllowlist: Bool) {
        let transport = AIProviderTransport()
        let secureRequest = try transport.makeRequest(
            binding: binding,
            instruction: "요약 제안",
            elements: [DocumentElement(
                elementID: "element-body", kind: "paragraph", order: 0,
                text: "전송 허용 본문", styleID: "body", evidenceIDs: []
            )],
            credential: "self-test-secret"
        )
        let remoteHTTPRejected: Bool
        do {
            _ = try transport.makeRequest(
                binding: AIRequestBinding(
                    documentID: binding.documentID, provider: binding.provider,
                    endpointIdentity: "http://provider.example/v1", model: binding.model, operation: binding.operation,
                    payloadScope: binding.payloadScope
                ),
                instruction: "요약", elements: [], credential: "secret"
            )
            remoteHTTPRejected = false
        } catch AIProviderTransportError.invalidEndpoint {
            remoteHTTPRejected = true
        }
        let endpointAllowed: (String, AIProviderKind) -> Bool = { value, provider in
            guard let url = URL(string: value) else { return false }
            return AIProviderTransport.endpointIsAllowed(url, provider: provider)
        }
        let brandedEndpoints: [(AIProviderKind, String)] = [
            (.openAI, "https://api.openai.com/v1"),
            (.anthropic, "https://api.anthropic.com"),
            (.gemini, "https://generativelanguage.googleapis.com"),
        ]
        let brandedAllowlist = brandedEndpoints.allSatisfy { provider, endpoint in
            endpointAllowed(endpoint, provider) && !endpointAllowed("https://other.example/v1", provider)
                && !endpointAllowed("http://127.0.0.1:11434/v1", provider)
        } && endpointAllowed("https://compatible.example/v1", .openAICompatible)
            && endpointAllowed("http://127.0.0.1:11434/v1", .openAICompatible)
        let responseContent = "{\"commands\":[{\"commandID\":\"parsed\",\"name\":\"replace-text\",\"targetElementID\":\"element-body\",\"value\":\"검토 결과\"}]}"
        let providerResponses: [(AIProviderKind, [String: Any])] = [
            (.openAI, ["choices": [["message": ["content": responseContent]]]]),
            (.openAICompatible, ["choices": [["message": ["content": responseContent]]]]),
            (.anthropic, ["content": [["text": responseContent]]]),
            (.gemini, ["candidates": [["content": ["parts": [["text": responseContent]]]]]]),
        ]
        let allResponsesParsed = try providerResponses.allSatisfy { provider, response in
            let data = try JSONSerialization.data(withJSONObject: response)
            return try transport.parseCommands(data, provider: provider).first?.commandID == "parsed"
        }
        let body = secureRequest.httpBody ?? Data()
        let secure = remoteHTTPRejected
            && secureRequest.url?.scheme == "https"
            && secureRequest.value(forHTTPHeaderField: "Authorization") == "Bearer self-test-secret"
            && body.contains(Data("전송 허용 본문".utf8))
            && allResponsesParsed
        return (secure, brandedAllowlist)
    }

    static func verifyScopedOperations(engine: AIGovernanceEngine) throws -> (
        scopedTargets: Bool, commands: AIGovernanceOperationSpecificReceipt,
        exactTablePath: Bool, cellOnlyMutation: Bool
    ) {
        let base = fixture()
        let scopedBinding = binding(for: .rewrite, scope: "selected-elements")
        let scoped = engine.grantConsent(scopedBinding, in: base)
        let validScoped = try engine.propose(
            binding: scopedBinding,
            commands: [AIProposalCommand(commandID: "scoped", name: "replace-text", targetElementID: "element-body", value: "범위 안")],
            allowedTargetElementIDs: ["element-body"], in: scoped
        )
        let scopedRejected = rejectsInvalidProposal {
            _ = try engine.propose(
                binding: scopedBinding,
                commands: [AIProposalCommand(commandID: "outside", name: "replace-text", targetElementID: "element-summary", value: "범위 밖")],
                allowedTargetElementIDs: ["element-body"], in: scoped
            )
        }
        let missingBinding = binding(for: .missingDataMarking, scope: "selected-elements")
        let missing = engine.grantConsent(missingBinding, in: base)
        let missingAccepted = try engine.propose(
            binding: missingBinding,
            commands: [AIProposalCommand(commandID: "missing", name: "replace-text", targetElementID: "element-summary", value: "[확인 필요] 담당 부서")],
            allowedTargetElementIDs: ["element-summary"], in: missing
        ).1.count == 1
        let missingRejected = rejectsInvalidProposal {
            _ = try engine.propose(
                binding: missingBinding,
                commands: [AIProposalCommand(commandID: "missing-invalid", name: "replace-text", targetElementID: "element-summary", value: "담당 부서")],
                allowedTargetElementIDs: ["element-summary"], in: missing
            )
        }
        let evidenceBinding = binding(for: .evidenceClaimCheck, scope: "evidence-and-claims")
        let evidence = engine.grantConsent(evidenceBinding, in: base)
        let evidenceAccepted = try engine.propose(
            binding: evidenceBinding,
            commands: [AIProposalCommand(commandID: "evidence", name: "evidence-check", targetElementID: "element-body", value: "근거 확인")],
            allowedTargetElementIDs: ["element-body"], in: evidence
        ).1.count == 1
        let evidenceRejected = rejectsInvalidProposal {
            _ = try engine.propose(
                binding: evidenceBinding,
                commands: [AIProposalCommand(commandID: "evidence-invalid", name: "evidence-check", targetElementID: "element-summary", value: "근거 없음")],
                allowedTargetElementIDs: ["element-summary"], in: evidence
            )
        }
        let tableBinding = binding(for: .tableChange, scope: "selected-elements")
        let table = engine.grantConsent(tableBinding, in: base)
        let tableCommand = AIProposalCommand(
            commandID: "table", name: "table-cell-update", targetElementID: "element-table",
            value: "변경", targetPath: "table:element-table/row:1/cell:0"
        )
        let tableProposal = try engine.propose(
            binding: tableBinding, commands: [tableCommand], allowedTargetElementIDs: ["element-table"], in: table
        )
        let tableApproved = try engine.approve(
            proposalID: tableProposal.0.aiProposalHistory.last!.proposalID, commandIDs: nil, in: tableProposal.0
        )
        let tableHTML = tableApproved.elements.first(where: { $0.elementID == "element-table" })?.contentHTML
        let expectedHTML = "<table><tbody><tr><th data-cell=\"header\">항목</th><th>값</th></tr><tr><td data-cell=\"target\">변경</td><td data-cell=\"keep\"><strong>보존</strong></td></tr></tbody></table>"
        let invalidPaths = [
            "table:other/row:1/cell:0", "table:element-table/row:-1/cell:0",
            "table:element-table/row:1/cell:-1", "table:element-table/row:1/cell:0/extra",
            "table:element-table/row:x/cell:0",
        ]
        let pathsRejected = invalidPaths.allSatisfy { path in
            rejectsInvalidProposal {
                _ = try engine.propose(
                    binding: tableBinding,
                    commands: [AIProposalCommand(commandID: "bad-path", name: "table-cell-update", targetElementID: "element-table", value: "금지", targetPath: path)],
                    allowedTargetElementIDs: ["element-table"], in: table
                )
            }
        }
        return (
            Set(validScoped.1.map(\.targetElementID)) == ["element-body"] && scopedRejected,
            AIGovernanceOperationSpecificReceipt(
                missingDataMarking: missingAccepted && missingRejected,
                evidenceClaimCheck: evidenceAccepted && evidenceRejected,
                tableCellUpdate: tableProposal.1.first?.targetPath == tableCommand.targetPath
            ),
            pathsRejected,
            tableHTML == expectedHTML
        )
    }

    static func binding(for operation: AIOperation, scope: String) -> AIRequestBinding {
        AIRequestBinding(
            documentID: "document-ac04", provider: .openAI,
            endpointIdentity: AIProviderCatalog.policy(for: .openAI).endpointIdentity,
            model: AIProviderCatalog.policy(for: .openAI).defaultModel,
            operation: operation, payloadScope: scope
        )
    }

    static func rejectsInvalidProposal(_ action: () throws -> Void) -> Bool {
        do {
            try action()
            return false
        } catch AIGovernanceError.invalidProposal {
            return true
        } catch {
            return false
        }
    }
}
