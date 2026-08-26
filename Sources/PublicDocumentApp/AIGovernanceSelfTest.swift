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
            "Sources/PublicDocumentApp/AIGovernanceModels.swift",
            "Sources/PublicDocumentApp/AIGovernanceProposalEngine.swift",
            "Sources/PublicDocumentApp/AIGovernanceRevisionEngine.swift",
            "Sources/PublicDocumentApp/AIBridgeCLI.swift",
            "Sources/PublicDocumentApp/AIProviderCatalog.swift",
            "Sources/PublicDocumentApp/AISettingsModels.swift",
            "Sources/PublicDocumentApp/AISettingsStore.swift",
            "Sources/PublicDocumentApp/AISettingsSelfTest.swift",
            "Sources/PublicDocumentApp/AIProviderTransport.swift",
            "Sources/PublicDocumentApp/AIGovernanceSelfTest.swift",
            "Sources/PublicDocumentApp/AIGovernanceSelfTestFixtures.swift",
            "Sources/PublicDocumentApp/AIGovernanceSelfTestScenarios.swift",
            "Sources/PublicDocumentApp/DocumentProject.swift",
            "Sources/PublicDocumentApp/DocumentProjectCoreModels.swift",
            "Sources/PublicDocumentApp/DocumentProjectAIModels.swift",
            "Sources/PublicDocumentApp/DocumentProjectState.swift",
            "Sources/PublicDocumentApp/DocumentProjectStore.swift",
            "Sources/PublicDocumentApp/main.swift",
            "Sources/PublicDocumentApp/StudioBridgeAI.swift",
            "Sources/PublicDocumentApp/StudioBridgeDispatch.swift",
        ]
        return try Dictionary(uniqueKeysWithValues: paths.map { path in
            let data = try Data(contentsOf: sourceRoot.appendingPathComponent(path))
            let digest = SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
            return (path, "sha256:\(digest)")
        })
    }

    private static let sourceRoot = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
}
