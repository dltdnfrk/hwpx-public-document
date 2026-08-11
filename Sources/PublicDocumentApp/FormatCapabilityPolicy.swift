import Foundation

enum FormatCapabilityPolicy {
    private struct CapabilityOccurrence {
        let capability: String
        let elementPath: String
    }

    private static let structuralOnlyCapabilities: Set<String> = ["table-row", "table-cell"]
    private static let frozenCombinations = [
        "paragraph+strong+emphasis+underline",
        "paragraph+keep-together",
        "unordered-list+list-item+strong",
        "table+table-row+table-cell+strong",
        "approval-grid+table-row+table-cell",
        "review-marker+strong",
    ]

    static func lossReports(
        project: DocumentProject,
        format: DocumentFormat
    ) throws -> [LossReport] {
        try lossReports(
            observations: observedCapabilities(project: project),
            format: format
        )
    }

    static func lossReports(
        observations: [ExportCapabilityObservation],
        format: DocumentFormat
    ) throws -> [LossReport] {
        let matrix = try loadMatrix()
        return try observations.compactMap { observation in
            if structuralOnlyCapabilities.contains(observation.capability) { return nil }
            guard let row = matrix[observation.capability] else {
                throw ExportError.invalidPackage("형식 기능 행 누락: \(observation.capability)")
            }
            return try report(row.classification(for: format), observation, format)
        }
    }

    static func observedCapabilities(
        project: DocumentProject
    ) throws -> [ExportCapabilityObservation] {
        let observations = try project.elements.sorted {
            $0.order == $1.order ? $0.elementID < $1.elementID : $0.order < $1.order
        }.flatMap { element in
            guard ExportCapabilities.authorableKinds.contains(element.kind) else {
                throw ExportError.unsupportedElementKind(element.kind)
            }
            return try capabilities(for: element).map { occurrence in
                ExportCapabilityObservation(
                    capability: occurrence.capability,
                    elementID: element.elementID,
                    elementPath: occurrence.elementPath
                )
            }
        }
        var seen = Set<ExportCapabilityObservation>()
        return observations.filter { seen.insert($0).inserted }
    }

    static func observedFrozenCombinations(
        project: DocumentProject
    ) throws -> [String] {
        try observedFrozenCombinations(observations: observedCapabilities(project: project))
    }

    static func observedFrozenCombinations(
        observations: [ExportCapabilityObservation]
    ) throws -> [String] {
        let grouped = Dictionary(grouping: observations, by: \.elementID)
        return frozenCombinations.filter { combination in
            let required = Set(combination.split(separator: "+").map(String.init))
            return grouped.values.contains { observations in
                required.isSubset(of: Set(observations.map(\.capability)))
            }
        }
    }

    private static func capabilities(for element: DocumentElement) throws -> [CapabilityOccurrence] {
        let document = try contentDocument(for: element)
        let inline = try inlineOccurrences(in: document, element: element)
        var capabilities = [CapabilityOccurrence(
            capability: element.kind,
            elementPath: path(for: element.kind, element: element)
        )]
        if ["table", "approval-grid"].contains(element.kind), let first = inline.first {
            capabilities.append(CapabilityOccurrence(
                capability: "table+rich-inline",
                elementPath: first.elementPath
            ))
        } else if let first = inline.first {
            capabilities.append(CapabilityOccurrence(
                capability: "rich-inline",
                elementPath: first.elementPath
            ))
        }
        capabilities.append(contentsOf: inline)
        capabilities.append(contentsOf: try keepTogetherOccurrences(in: document, element: element))
        capabilities.append(contentsOf: try listOccurrences(in: document, element: element))
        capabilities.append(contentsOf: try tableStructureOccurrences(in: document, element: element))
        var seen = Set<String>()
        return capabilities.filter { seen.insert("\($0.capability)\u{0}\($0.elementPath)").inserted }
    }

    private static func contentDocument(for element: DocumentElement) throws -> XMLDocument {
        do {
            return try XMLDocument(
                xmlString: "<html><body>\(element.contentHTML)</body></html>",
                options: .documentTidyHTML
            )
        } catch {
            throw ExportError.invalidPackage("\(element.elementID) 작성 구조")
        }
    }

    private static func inlineOccurrences(
        in document: XMLDocument,
        element: DocumentElement
    ) throws -> [CapabilityOccurrence] {
        try document.nodes(forXPath: "//body//*").enumerated().flatMap { index, node -> [CapabilityOccurrence] in
            guard let node = node as? XMLElement else { return [] }
            let name = node.name?.lowercased() ?? ""
            let style = node.attribute(forName: "style")?.stringValue ?? ""
            var capabilities: [String] = []
            if ["b", "strong"].contains(name) { capabilities.append("strong") }
            if ["i", "em"].contains(name) { capabilities.append("emphasis") }
            if name == "u" { capabilities.append("underline") }
            if name == "font", node.attribute(forName: "face")?.stringValue?.isEmpty == false {
                capabilities.append("font-face")
            }
            if name == "font", node.attribute(forName: "size")?.stringValue?.isEmpty == false {
                capabilities.append("font-size")
            }
            if containsStyleProperty("font-family", in: style) { capabilities.append("font-face") }
            if containsStyleProperty("font-size", in: style) { capabilities.append("font-size") }
            guard !capabilities.isEmpty else { return [] }
            let elementPath = inlinePath(for: node, element: element, fallbackIndex: index)
            return capabilities.map {
                CapabilityOccurrence(capability: $0, elementPath: elementPath)
            }
        }
    }

    private static func containsStyleProperty(_ property: String, in style: String) -> Bool {
        let escaped = NSRegularExpression.escapedPattern(for: property)
        return style.range(
            of: #"(?:^|;)\s*"# + escaped + #"\s*:"#,
            options: [.regularExpression, .caseInsensitive]
        ) != nil
    }

    private static func inlinePath(
        for node: XMLElement,
        element: DocumentElement,
        fallbackIndex: Int
    ) -> String {
        let descendants = (try? node.nodes(forXPath: ".//*[@data-inline-id]")) ?? []
        let descendantInlineID = descendants.compactMap { $0 as? XMLElement }.first?
            .attribute(forName: "data-inline-id")?.stringValue
        let inlineID = node.attribute(forName: "data-inline-id")?.stringValue
            ?? descendantInlineID
        let base = "elements/\(element.order)"
        if ["table", "approval-grid"].contains(element.kind) {
            return inlineID.map { "\(base)/table/inlines/\($0)" }
                ?? "\(base)/table/rich-inlines/\(fallbackIndex)"
        }
        return inlineID.map { "\(base)/inlines/\($0)" }
            ?? "\(base)/rich-inlines/\(fallbackIndex)"
    }

    private static func keepTogetherOccurrences(
        in document: XMLDocument,
        element: DocumentElement
    ) throws -> [CapabilityOccurrence] {
        try document.nodes(
            forXPath: #"//*[contains(concat(' ', normalize-space(@class), ' '), ' keep-phrase ')]"#
        ).enumerated().compactMap { index, node in
            guard let node = node as? XMLElement else { return nil }
            return CapabilityOccurrence(
                capability: "keep-together",
                elementPath: inlinePath(for: node, element: element, fallbackIndex: index)
            )
        }
    }

    private static func report(
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

    private static func path(for capability: String, element: DocumentElement) -> String {
        switch capability {
        case "metadata", "heading", "review-marker":
            return "elements/\(element.order)/style"
        default:
            return "elements/\(element.order)"
        }
    }

    private static func listOccurrences(
        in document: XMLDocument,
        element: DocumentElement
    ) throws -> [CapabilityOccurrence] {
        return try document.nodes(forXPath: "//ul").enumerated().flatMap { listIndex, list in
            let listPath = "elements/\(element.order)/lists/\(listIndex)"
            let items = try list.nodes(forXPath: "./li").enumerated().map { itemIndex, _ in
                CapabilityOccurrence(
                    capability: "list-item",
                    elementPath: "\(listPath)/items/\(itemIndex)"
                )
            }
            return [CapabilityOccurrence(capability: "unordered-list", elementPath: listPath)] + items
        }
    }

    private static func tableStructureOccurrences(
        in document: XMLDocument,
        element: DocumentElement
    ) throws -> [CapabilityOccurrence] {
        guard ["table", "approval-grid"].contains(element.kind) else { return [] }
        return try document.nodes(forXPath: "//tr").enumerated().flatMap { rowIndex, row in
            let rowPath = "elements/\(element.order)/table/rows/\(rowIndex)"
            let cells = try row.nodes(forXPath: "./th | ./td").enumerated().map { cellIndex, _ in
                CapabilityOccurrence(
                    capability: "table-cell",
                    elementPath: "\(rowPath)/cells/\(cellIndex)"
                )
            }
            return [CapabilityOccurrence(capability: "table-row", elementPath: rowPath)] + cells
        }
    }

    private static func fallback(
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

    private static func loadMatrix() throws -> [String: FormatCapabilityRow] {
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
