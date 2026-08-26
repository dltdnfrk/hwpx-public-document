import Foundation

extension FormatCapabilityPolicy {
    static func report(
        _ rawClassification: String,
        _ observation: ExportCapabilityObservation,
        _ format: DocumentFormat
    ) throws -> LossReport? {
        guard rawClassification != "lossless" else { return nil }
        let classification: LossClassification
        switch rawClassification {
        case LossClassification.visualOnlyFlattening.rawValue:
            classification = .visualOnlyFlattening
        case LossClassification.semanticLoss.rawValue:
            classification = .semanticLoss
        default:
            throw ExportError.invalidPackage("알 수 없는 손실 등급: \(rawClassification)")
        }
        return LossReport(
            format: format,
            capability: observation.capability,
            elementID: observation.elementID,
            elementPath: observation.elementPath,
            classification: classification,
            fallback: try fallback(
                for: observation.capability,
                classification: classification,
                format: format
            ),
            requiresConsent: classification == .visualOnlyFlattening,
            evidenceSource: .preflightPolicy
        )
    }

    static func fallback(
        for capability: String,
        classification: LossClassification,
        format: DocumentFormat
    ) throws -> String {
        switch capability {
        case "keep-together":
            return "문구 묶음 배치는 생략하고 텍스트와 강조를 편집 가능하게 보존합니다."
        case "unordered-list", "list-item":
            return "목록 항목과 계층을 보존하는 어댑터가 준비될 때까지 이 형식을 차단합니다."
        case "table" where classification == .semanticLoss,
             "approval-grid" where classification == .semanticLoss,
             "table+rich-inline" where classification == .semanticLoss:
            return "고정된 rhwp 공공문서 어댑터가 이 셀 구조를 아직 보존할 수 없습니다."
        case "formula" where format == .markdown:
            return "편집 가능한 수식 의미를 보존하려면 HWPX, HWP 또는 DOCX로 내보내세요."
        case "formula":
            return "고정된 rhwp 공공문서 어댑터가 앱 수식 의미를 아직 매핑하지 못합니다."
        case "strong":
            return "굵게 서식은 일반 텍스트로 변환하고 내용은 편집 가능하게 보존합니다."
        case "emphasis":
            return "기울임 서식은 일반 텍스트로 변환하고 내용은 편집 가능하게 보존합니다."
        case "underline":
            return "밑줄 서식은 일반 텍스트로 변환하고 내용은 편집 가능하게 보존합니다."
        case "font-face":
            return "선택 글꼴은 대상 형식의 기본 글꼴로 대체하고 내용은 편집 가능하게 보존합니다."
        case "font-size":
            return "선택 글자 크기는 대상 형식의 기본 크기로 대체하고 내용은 편집 가능하게 보존합니다."
        case "metadata", "heading", "review-marker":
            return "텍스트는 편집 가능하게 보존하고 앱 전용 시각 스타일은 rhwp 본문 스타일로 변환합니다."
        case "rich-inline", "table+rich-inline":
            return "서식은 일반 텍스트로 변환하고 내용은 편집 가능하게 보존합니다."
        default:
            throw ExportError.invalidPackage("손실 대체 정책 누락: \(capability)")
        }
    }

    static func loadMatrix() throws -> [String: FormatCapabilityRow] {
        let relativePath = "Capabilities/format-capabilities-1.0.0.json"
        let local = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
            .appendingPathComponent("Resources/\(relativePath)")
        let bundled = Bundle.main.resourceURL?.appendingPathComponent(relativePath)
        guard let source = [bundled, local].compactMap({ $0 }).first(where: {
            FileManager.default.fileExists(atPath: $0.path)
        }) else {
            throw ExportError.invalidPackage("형식 기능 매트릭스 누락")
        }
        let resource = try JSONDecoder().decode(
            FormatCapabilityResource.self,
            from: Data(contentsOf: source)
        )
        guard resource.manifestVersion == ExportCapabilities.manifestVersion else {
            throw ExportError.invalidPackage("형식 기능 매트릭스 버전")
        }
        let pairs = resource.matrix.map { ($0.capability, $0) }
        guard Set(pairs.map(\.0)).count == pairs.count else {
            throw ExportError.invalidPackage("형식 기능 행 중복")
        }
        return Dictionary(uniqueKeysWithValues: pairs)
    }
}
