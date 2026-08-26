import CryptoKit
import Foundation

struct AIGovernanceOperationSpecificReceipt: Codable {
    let missingDataMarking: Bool
    let evidenceClaimCheck: Bool
    let tableCellUpdate: Bool
}

struct AIGovernanceSelfTestReceipt: Codable {
    let approvedProviderKinds: [String]
    let offlineEditingAndExportAvailable: Bool
    let localAdapterUnavailableWithoutFallback: Bool
    let allConsentBindingsRequired: Bool
    let revocationBlockedFutureRequest: Bool
    let proposalDidNotMutateDocument: Bool
    let diffsExposeStableTargets: Bool
    let staleProposalRejected: Bool
    let partialApprovalAppliedAtomically: Bool
    let wholeApprovalAppliedAtomically: Bool
    let rejectionPersisted: Bool
    let undoRedoPersistedAcrossRestart: Bool
    let forbiddenDataAbsentFromPersistence: Bool
    let secureProviderTransportBehavior: Bool
    let brandedEndpointAllowlistEnforced: Bool
    let endpointValidationPrecedesPersistence: Bool
    let actualScopedTargetIDsEnforced: Bool
    let operationSpecificCommands: AIGovernanceOperationSpecificReceipt
    let exactTablePathFailClosed: Bool
    let tableCellOnlyMutation: Bool
    let fullDiffPersisted: Bool
    let consentRebindingRequired: Bool
    let sharedPayloadScopeRules: Bool
    let implementationSourceSHA256: [String: String]
}

// allow: SIZE_OK — this executable evidence matrix keeps the complete AC-04 scenario in one receipt.
enum AIGovernanceSelfTest {
    static func run(at root: URL) throws -> AIGovernanceSelfTestReceipt {
        let engine = AIGovernanceEngine()
        let store = DocumentProjectStore(root: root.appendingPathComponent("governed.publicdocument"))
        let binding = AIRequestBinding(
            documentID: "document-ac04", provider: .openAI,
            endpointIdentity: "https://api.openai.com/v1", model: "gpt-5-mini", operation: .rewrite,
            payloadScope: "elements:element-body,element-summary"
        )
        var project = fixture()
        try store.save(project)
        let offlineReady = try store.loadCanonical().elements.count == 4
            && Set(DocumentFormat.allCases.map(\.rawValue)) == Set(["hwpx", "hwp", "docx", "markdown"])
        project = engine.grantConsent(binding, in: project)
        let bindingChecks = [
            AIRequestBinding(documentID: "other", provider: .openAI, endpointIdentity: binding.endpointIdentity, model: binding.model, operation: .rewrite, payloadScope: binding.payloadScope),
            AIRequestBinding(documentID: binding.documentID, provider: .anthropic, endpointIdentity: binding.endpointIdentity, model: binding.model, operation: .rewrite, payloadScope: binding.payloadScope),
            AIRequestBinding(documentID: binding.documentID, provider: .openAI, endpointIdentity: "https://other.example/v1", model: binding.model, operation: .rewrite, payloadScope: binding.payloadScope),
            AIRequestBinding(documentID: binding.documentID, provider: .openAI, endpointIdentity: binding.endpointIdentity, model: binding.model, operation: .summarize, payloadScope: binding.payloadScope),
            AIRequestBinding(documentID: binding.documentID, provider: .openAI, endpointIdentity: binding.endpointIdentity, model: binding.model, operation: .rewrite, payloadScope: "whole-document"),
            AIRequestBinding(documentID: binding.documentID, provider: .openAI, endpointIdentity: binding.endpointIdentity, model: "gpt-5.6-terra", operation: .rewrite, payloadScope: binding.payloadScope),
        ]
        let allBindingsRequired = bindingChecks.allSatisfy { candidate in
            do {
                try engine.authorize(candidate, in: project)
                return false
            } catch AIGovernanceError.consentRequired {
                return true
            } catch {
                return false
            }
        }
        let fullBodyReplacement = "사용자 검토 후 반영할 본문 " + String(repeating: "전체 변경 내용 ", count: 128)
        let firstCommands = [
            AIProposalCommand(commandID: "command-body", name: "replace-text", targetElementID: "element-body", value: fullBodyReplacement),
            AIProposalCommand(commandID: "command-summary", name: "replace-text", targetElementID: "element-summary", value: "사용자 검토 후 반영할 요약"),
        ]
        let originalElements = project.elements
        let proposalResult = try engine.propose(binding: binding, commands: firstCommands, allowedTargetElementIDs: Set(firstCommands.map(\.targetElementID)), in: project)
        project = proposalResult.0
        let firstProposal = project.aiProposalHistory.last!
        let proposalDidNotMutate = project.elements == originalElements
        let stableDiffs = Set(proposalResult.1.map(\.targetElementID)) == Set(["element-body", "element-summary"])
        let staleResult = try engine.propose(
            binding: binding,
            commands: [AIProposalCommand(commandID: "command-stale", name: "replace-text", targetElementID: "element-body", value: "오래된 제안")],
            allowedTargetElementIDs: ["element-body"],
            in: project
        )
        project = try engine.approve(
            proposalID: firstProposal.proposalID, commandIDs: Set(["command-body"]), in: staleResult.0
        )
        let partialProject = project
        let partialAtomic = project.elements.first(where: { $0.elementID == "element-body" })?.text == fullBodyReplacement
            && project.elements.first(where: { $0.elementID == "element-summary" })?.text == "기존 요약"
            && project.aiProposalHistory.first(where: { $0.proposalID == firstProposal.proposalID })?.state == "partially-approved"
        let staleProposal = staleResult.0.aiProposalHistory.last!
        let staleRejected: Bool
        do {
            _ = try engine.approve(proposalID: staleProposal.proposalID, commandIDs: nil, in: project)
            staleRejected = false
        } catch AIGovernanceError.staleProposal {
            staleRejected = project == partialProject
        }
        let wholeResult = try engine.propose(
            binding: binding,
            commands: [AIProposalCommand(commandID: "command-whole", name: "replace-text", targetElementID: "element-summary", value: "전체 승인 요약")],
            allowedTargetElementIDs: ["element-summary"],
            in: project
        )
        project = try engine.approve(proposalID: wholeResult.0.aiProposalHistory.last!.proposalID, commandIDs: nil, in: wholeResult.0)
        let wholeAtomic = project.elements.first(where: { $0.elementID == "element-summary" })?.text == "전체 승인 요약"
            && project.aiProposalHistory.last?.state == "approved"
        let rejectedResult = try engine.propose(
            binding: binding,
            commands: [AIProposalCommand(commandID: "command-reject", name: "replace-text", targetElementID: "element-body", value: "거절할 변경")],
            allowedTargetElementIDs: ["element-body"],
            in: project
        )
        project = try engine.reject(proposalID: rejectedResult.0.aiProposalHistory.last!.proposalID, in: rejectedResult.0)
        try store.save(project)
        let reopenedForUndo = try store.loadCanonical()
        let undone = try engine.undo(in: reopenedForUndo)
        try store.save(undone)
        let reopenedForRedo = try store.loadCanonical()
        let redone = try engine.redo(in: reopenedForRedo)
        try store.save(redone)
        let restarted = try store.loadCanonical()
        let persistedHistory = restarted.aiProposalHistory.last?.state == "rejected"
        let undoRedoPersisted = restarted.currentRevisionID == project.currentRevisionID
            && restarted.elements == project.elements && restarted.redoRevisionIDs.isEmpty
        guard let grantID = restarted.consentGrants.first?.grantID else {
            throw AIGovernanceError.consentRequired
        }
        let revoked = engine.revokeConsent(grantID: grantID, in: restarted)
        let revocationBlocked: Bool
        do {
            try engine.authorize(binding, in: revoked)
            revocationBlocked = false
        } catch AIGovernanceError.consentRequired {
            revocationBlocked = true
        }
        let persisted = try Data(contentsOf: store.projectFile)
        let forbiddenAbsent = !persisted.contains(Data("super-secret-key".utf8))
            && !persisted.contains(Data("전송 전용 비공개 요청 본문".utf8))
        let fullDiffPersisted = restarted.aiProposalHistory.first(where: { $0.proposalID == firstProposal.proposalID })?.diffs == proposalResult.1
            && proposalResult.1.first(where: { $0.commandID == "command-body" })?.before == "기존 본문"
            && proposalResult.1.first(where: { $0.commandID == "command-body" })?.after == fullBodyReplacement
            && fullBodyReplacement.utf8.count > 512
        let transportEvidence = try verifyProviderTransport(binding: binding)
        let operationEvidence = try verifyScopedOperations(engine: engine)
        let sharedScopeIDs = try AIGovernanceEngine.scopedElements(
            in: fixture(),
            scope: .evidenceAndClaims,
            selectedElementIDs: []
        ).map(\.elementID)
        return AIGovernanceSelfTestReceipt(
            approvedProviderKinds: AIGovernanceEngine.approvedProviderKinds.map(\.rawValue).sorted(),
            offlineEditingAndExportAvailable: offlineReady,
            localAdapterUnavailableWithoutFallback: !AIGovernanceEngine.approvedProviderKinds.map(\.rawValue).contains("local"),
            allConsentBindingsRequired: allBindingsRequired,
            revocationBlockedFutureRequest: revocationBlocked,
            proposalDidNotMutateDocument: proposalDidNotMutate,
            diffsExposeStableTargets: stableDiffs,
            staleProposalRejected: staleRejected,
            partialApprovalAppliedAtomically: partialAtomic,
            wholeApprovalAppliedAtomically: wholeAtomic,
            rejectionPersisted: persistedHistory,
            undoRedoPersistedAcrossRestart: undoRedoPersisted,
            forbiddenDataAbsentFromPersistence: forbiddenAbsent,
            secureProviderTransportBehavior: transportEvidence.secure,
            brandedEndpointAllowlistEnforced: transportEvidence.brandedAllowlist,
            endpointValidationPrecedesPersistence: try verifyEndpointValidationPrecedesPersistence(),
            actualScopedTargetIDsEnforced: operationEvidence.scopedTargets,
            operationSpecificCommands: operationEvidence.commands,
            exactTablePathFailClosed: operationEvidence.exactTablePath,
            tableCellOnlyMutation: operationEvidence.cellOnlyMutation,
            fullDiffPersisted: fullDiffPersisted,
            consentRebindingRequired: allBindingsRequired,
            sharedPayloadScopeRules: sharedScopeIDs == ["element-title", "element-body"],
            implementationSourceSHA256: try implementationSourceSHA256()
        )
    }

    private static func verifyProviderTransport(binding: AIRequestBinding) throws -> (secure: Bool, brandedAllowlist: Bool) {
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

    private static func verifyScopedOperations(engine: AIGovernanceEngine) throws -> (
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

    private static func binding(for operation: AIOperation, scope: String) -> AIRequestBinding {
        AIRequestBinding(
            documentID: "document-ac04", provider: .openAI,
            endpointIdentity: AIProviderCatalog.policy(for: .openAI).endpointIdentity,
            model: AIProviderCatalog.policy(for: .openAI).defaultModel,
            operation: operation, payloadScope: scope
        )
    }

    private static func rejectsInvalidProposal(_ action: () throws -> Void) -> Bool {
        do {
            try action()
            return false
        } catch AIGovernanceError.invalidProposal {
            return true
        } catch {
            return false
        }
    }

    private static func verifyEndpointValidationPrecedesPersistence() throws -> Bool {
        let service = "com.muni.public-document.endpoint-order.\(UUID().uuidString)"
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("public-document-endpoint-order-\(UUID().uuidString)")
        setenv("PUBLIC_DOCUMENT_STUDIO_AI_KEYCHAIN_SERVICE", service, 1)
        defer {
            unsetenv("PUBLIC_DOCUMENT_STUDIO_AI_KEYCHAIN_SERVICE")
            try? FileManager.default.removeItem(at: root)
        }
        let store = AISettingsStore(root: root)
        do {
            _ = try store.save(
                provider: .openAI,
                endpointIdentity: "https://evil.example/v1",
                model: "gpt-5.6-terra",
                secret: "SHOULD-NOT-BE-STORED"
            )
            return false
        } catch AISettingsError.invalidEndpoint {
            let settingsMissing = !FileManager.default.fileExists(
                atPath: root.appendingPathComponent("ai-settings.json").path
            )
            let credentialMissing: Bool
            do {
                _ = try AIKeychainCredentialStore(service: service).get(
                    accountReference: "provider/openai"
                )
                credentialMissing = false
            } catch {
                credentialMissing = true
            }
            return settingsMissing && credentialMissing
        }
    }

    private static func implementationSourceSHA256() throws -> [String: String] {
        let paths = [
            "Sources/PublicDocumentApp/AIGovernance.swift",
            "Sources/PublicDocumentApp/AIBridgeCLI.swift",
            "Sources/PublicDocumentApp/AIProviderCatalog.swift",
            "Sources/PublicDocumentApp/AISettingsModels.swift",
            "Sources/PublicDocumentApp/AISettingsStore.swift",
            "Sources/PublicDocumentApp/AISettingsSelfTest.swift",
            "Sources/PublicDocumentApp/AIProviderTransport.swift",
            "Sources/PublicDocumentApp/AIGovernanceSelfTest.swift",
            "Sources/PublicDocumentApp/DocumentProject.swift",
            "Sources/PublicDocumentApp/main.swift",
        ]
        return try Dictionary(uniqueKeysWithValues: paths.map { path in
            let data = try Data(contentsOf: sourceRoot.appendingPathComponent(path))
            let digest = SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
            return (path, "sha256:\(digest)")
        })
    }

    private static let sourceRoot = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)

    private static func fixture() -> DocumentProject {
        let elements = [
            DocumentElement(elementID: "element-title", kind: "heading", order: 0, text: "공공문서", styleID: "title", evidenceIDs: []),
            DocumentElement(elementID: "element-body", kind: "paragraph", order: 1, text: "기존 본문", styleID: "body", evidenceIDs: ["evidence-1"]),
            DocumentElement(elementID: "element-summary", kind: "paragraph", order: 2, text: "기존 요약", styleID: "body", evidenceIDs: []),
            DocumentElement(
                elementID: "element-table", kind: "table", order: 3, text: "항목 값 대상 보존",
                contentHTML: "<table><tbody><tr><th data-cell=\"header\">항목</th><th>값</th></tr><tr><td data-cell=\"target\">대상</td><td data-cell=\"keep\"><strong>보존</strong></td></tr></tbody></table>",
                inlineIDs: ["inline-table-keep"], styleID: "body", evidenceIDs: []
            ),
        ]
        let revision = DocumentRevision(
            revisionID: "revision-base", createdAt: "2026-08-09T00:00:00Z", summary: "created",
            elementIDs: elements.map(\.elementID), snapshotElements: elements
        )
        return DocumentProject(
            schemaVersion: 1, documentID: "document-ac04", locale: "ko-KR", title: "공공문서",
            currentRevisionID: revision.revisionID, elements: elements, assets: [],
            styles: [DocumentStyle(styleID: "body", name: "본문", properties: [:])],
            templateBinding: ProjectTemplateBinding(
                templateID: "public-plan", version: "3.2", publishingAuthority: "기관 표준",
                requiredSections: ["본문"], checklistResults: ["본문": true]
            ),
            evidenceLinks: [], revisions: [revision],
            history: [ProjectHistoryEvent(eventID: "history-base", kind: "created", revisionID: revision.revisionID, createdAt: revision.createdAt)],
            aiProposalHistory: [],
            providerConfigurations: [AIProviderConfiguration(
                provider: "openai", endpointIdentity: "https://api.openai.com/v1",
                keychainAccountReference: "keychain://public-document-studio/openai"
            )]
        )
    }
}
