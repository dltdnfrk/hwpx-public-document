import Foundation

enum TypstSidecar {
    static func write(project: DocumentProject, destination: URL) {
        do {
            try FileManager.default.createDirectory(at: destination, withIntermediateDirectories: true)
            let source = typstSource(project: project)
            let typ = destination.appendingPathComponent("document.typ")
            try source.write(to: typ, atomically: true, encoding: .utf8)
            guard let typst = resolveTypst() else { return }
            let pdf = destination.appendingPathComponent("document.pdf")
            let process = Process()
            process.executableURL = typst
            process.arguments = ["compile", typ.path, pdf.path]
            process.standardOutput = Pipe()
            process.standardError = Pipe()
            try process.run()
            process.waitUntilExit()
        } catch {
            return
        }
    }

    static func typstSource(project: DocumentProject) -> String {
        var lines = [
            "#set page(paper: \"a4\", margin: (top: 20mm, right: 20mm, bottom: 10mm, left: 20mm))",
            "#set text(font: (\"Apple Myungjo\", \"Apple SD Gothic Neo\"), size: 15pt, lang: \"ko\")",
            "#align(center, text(16pt, weight: \"bold\")[\(escape(project.title))])",
            "#v(1em)",
        ]
        for element in project.elements.sorted(by: { $0.order < $1.order }) {
            let text = escape(element.text)
            guard !text.isEmpty else { continue }
            if element.kind == "heading" || element.styleID == "style-section-heading" {
                lines.append("#text(16pt, weight: \"bold\")[\(text)]")
            } else {
                lines.append(text)
            }
            lines.append("#v(0.6em)")
        }
        lines.append("// HWPX 대체가 아닌 미리보기 사이드카")
        return lines.joined(separator: "\n") + "\n"
    }

    private static func escape(_ value: String) -> String {
        value.replacingOccurrences(of: "\\", with: "\\\\")
            .replacingOccurrences(of: "#", with: "\\#")
            .replacingOccurrences(of: "[", with: "\\[")
            .replacingOccurrences(of: "]", with: "\\]")
    }

    private static func resolveTypst() -> URL? {
        let candidates = [
            "/opt/homebrew/bin/typst",
            "/usr/local/bin/typst",
            "/usr/bin/typst",
        ]
        return candidates.map(URL.init(fileURLWithPath:)).first {
            FileManager.default.isExecutableFile(atPath: $0.path)
        }
    }
}
