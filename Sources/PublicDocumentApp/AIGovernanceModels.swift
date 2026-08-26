import Foundation

enum AIProviderKind: String, CaseIterable, Codable {
    case anthropic
    case gemini
    case openAI = "openai"
    case openAICompatible = "openai-compatible"
}

enum AIOperation: String, Codable {
    case sourceGroundedDraft = "source-grounded-draft"
    case templateCompletion = "template-completion"
    case missingDataMarking = "missing-data-marking"
    case summarize
    case rewrite
    case translate
    case publicLanguageCorrection = "public-language-correction"
    case styleCorrection = "style-correction"
    case tableChange = "table-change"
    case evidenceClaimCheck = "evidence-claim-check"
    case freeForm = "free-form"
}

enum AIPayloadScope: String, Codable {
    case selectedElements = "selected-elements"
    case evidenceAndClaims = "evidence-and-claims"
    case wholeDocument = "whole-document"
}

struct AIRequestBinding: Equatable {
    let documentID: String
    let provider: AIProviderKind
    let endpointIdentity: String
    let model: String
    let operation: AIOperation
    let payloadScope: String

    init(
        documentID: String,
        provider: AIProviderKind,
        endpointIdentity: String,
        model: String,
        operation: AIOperation,
        payloadScope: String
    ) {
        self.documentID = documentID
        self.provider = provider
        self.endpointIdentity = endpointIdentity
        self.model = model
        self.operation = operation
        self.payloadScope = payloadScope
    }
}

enum AIGovernanceError: Error, LocalizedError {
    case consentRequired
    case staleProposal
    case invalidProposal
    case proposalUnavailable
    case undoUnavailable
    case redoUnavailable

    var errorDescription: String? {
        switch self {
        case .consentRequired: return "문서, 제공자, 엔드포인트, 작업 및 전송 범위에 맞는 동의가 필요합니다."
        case .staleProposal: return "제안 기준 리비전이 현재 문서와 달라 적용할 수 없습니다."
        case .invalidProposal: return "스키마 또는 대상 요소가 유효하지 않아 제안을 적용할 수 없습니다."
        case .proposalUnavailable: return "검토할 AI 제안을 찾을 수 없습니다."
        case .undoUnavailable: return "실행 취소할 AI 리비전이 없습니다."
        case .redoUnavailable: return "다시 실행할 AI 리비전이 없습니다."
        }
    }
}

struct AIProposalDiff: Codable, Equatable {
    let commandID: String
    let targetElementID: String
    let before: String
    let after: String
    let targetPath: String?
}
