import Foundation

extension FormatCapabilityPolicy {
    private struct CapabilityOccurrence {
        let capability: String
        let elementPath: String
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
}
