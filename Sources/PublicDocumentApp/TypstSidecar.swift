import Foundation

enum TypstSidecar {
    static func write(project: DocumentProject, destination: URL) -> TypstSidecarReceipt {
        var sourceFile: String?
        do {
            try FileManager.default.createDirectory(at: destination, withIntermediateDirectories: true)
            let typ = destination.appendingPathComponent("document.typ")
            let pdf = destination.appendingPathComponent("document.pdf")
            guard !FileManager.default.fileExists(atPath: typ.path),
                  !FileManager.default.fileExists(atPath: pdf.path)
            else {
                // Existing sidecars are unverified, not outputs of this snapshot.
                return TypstSidecarReceipt(state: "skipped", sourceFile: nil, pdfFile: nil, diagnosticCode: "destination-exists")
            }
            let source = try typstSource(project: project)
            try Data(source.utf8).write(to: typ, options: .withoutOverwriting)
            sourceFile = typ.lastPathComponent
            guard source.utf8.count <= 8 * 1024 * 1024 else {
                return TypstSidecarReceipt(state: "source-only", sourceFile: sourceFile, pdfFile: nil, diagnosticCode: "source-size-limit")
            }
            guard let typst = resolveTypst() else {
                return TypstSidecarReceipt(state: "source-only", sourceFile: sourceFile, pdfFile: nil, diagnosticCode: "missing-typst-engine")
            }
            let process = Process()
            process.executableURL = typst
            // Compile to a pipe so Typst cannot overwrite an existing destination PDF.
            process.arguments = ["compile", "--format", "pdf", typ.path, "-"]
            let output = Pipe()
            process.standardOutput = output
            process.standardError = FileHandle.standardError
            try process.run()
            let data = output.fileHandleForReading.readDataToEndOfFile()
            process.waitUntilExit()
            guard process.terminationStatus == 0, data.starts(with: Data("%PDF-".utf8)) else {
                return TypstSidecarReceipt(state: "failed", sourceFile: sourceFile, pdfFile: nil, diagnosticCode: "typst-compile-failed", diagnosticMessage: "Typst exit status: \(process.terminationStatus)")
            }
            try data.write(to: pdf, options: .withoutOverwriting)
            return TypstSidecarReceipt(state: "published", sourceFile: sourceFile, pdfFile: pdf.lastPathComponent, diagnosticCode: "")
        } catch {
            return TypstSidecarReceipt(state: "failed", sourceFile: sourceFile, pdfFile: nil, diagnosticCode: "sidecar-write-failed", diagnosticMessage: error.localizedDescription)
        }
    }

    static func typstSource(project: DocumentProject) throws -> String {
        let profile = try OfficialDocumentProfile.load()
        guard let title = profile.presets["style-title"],
              let body = profile.presets["style-body"]
        else {
            throw ExportError.invalidPackage("official layout profile is missing Typst presets")
        }
        var lines = [
            "#set page(paper: \"a4\", margin: (top: \(millimeters(profile.page.top))mm, right: \(millimeters(profile.page.right))mm, bottom: \(millimeters(profile.page.bottom))mm, left: \(millimeters(profile.page.left))mm))",
            "#set text(font: (\"\(body.macFont)\", \"\(title.macFont)\"), size: \(body.pointSize)pt, lang: \"ko\")",
            "#set par(leading: 0.68em)",
            "#align(center, text(\(title.pointSize)pt, weight: \"bold\")[\(escape(project.title))])",
            "#v(1em)",
        ]
        for element in project.elements.sorted(by: { $0.order < $1.order }) {
            if element.styleID == "style-title" && element.text == project.title { continue }
            if element.kind == "table" || element.kind == "approval-grid" {
                lines.append(contentsOf: tableLines(element))
                lines.append("#v(0.6em)")
                continue
            }
            let text = element.text.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !text.isEmpty else { continue }
            if element.kind == "heading" || element.styleID == "style-section-heading" {
                let heading = profile.presets["style-section-heading"] ?? title
                lines.append("#text(\(heading.pointSize)pt, weight: \"bold\")[\(escape(text))]")
            } else {
                for line in OfficialTypeset.lines(text) {
                    if let hang = OfficialTypeset.hanging(line) {
                        let pad = hang.left > hang.hanging ? "1.15em" : "0em"
                        lines.append("#pad(left: \(pad))[#par(hanging-indent: 1.4em)[\(escape(line))]]")
                    } else {
                        lines.append(escape(line))
                    }
                }
            }
            lines.append("#v(0.45em)")
        }
        lines.append("// HWPX 대체가 아닌 미리보기 사이드카")
        return lines.joined(separator: "\n") + "\n"
    }

    private static func tableLines(_ element: DocumentElement) -> [String] {
        guard let rows = try? ExportSerializers.tableRows(element), let first = rows.first else {
            return OfficialTypeset.lines(element.text).map(escape)
        }
        let cols = rows.map(\.count).max() ?? first.count
        var out = ["#table(columns: \(cols), stroke: 0.5pt, inset: 8pt,"]
        for (index, row) in rows.enumerated() {
            let cells = row.map { "[\(escape($0))]" }.joined(separator: ", ")
            out.append("  \(cells)\(index == rows.count - 1 ? ")" : ",")")
        }
        return out
    }

    private static func escape(_ value: String) -> String {
        value.replacingOccurrences(of: "\\", with: "\\\\")
            .replacingOccurrences(of: "#", with: "\\#")
            .replacingOccurrences(of: "[", with: "\\[")
            .replacingOccurrences(of: "]", with: "\\]")
    }

    private static func millimeters(_ twips: Int) -> String {
        String(
            format: "%.2f",
            locale: Locale(identifier: "en_US_POSIX"),
            Double(twips) * 25.4 / 1440.0
        )
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
