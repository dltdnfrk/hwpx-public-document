import CryptoKit
import Foundation

enum OfficialStyleBinding {
    static let presetIDs = [
        "style-title",
        "style-section-heading",
        "style-body",
        "style-body-detail",
        "style-reference-note",
        "style-annotation",
        "style-reference",
    ]
    static let markers = ["□ ", "○", "-", "※", "*"]

    static func json() throws -> Data {
        try JSONSerialization.data(
            withJSONObject: [
                "default_font": "AppleMyungjo",
                "preset_ids": presetIDs,
                "markers": markers,
                "guidebook_list": ["□ ", "○", "-", "※", "*"],
                "statutory_list": ["1. ", "가. ", "1) ", "가) ", "(1) ", "(가) ", "① ", "㉮ "],
            ],
            options: [.sortedKeys]
        )
    }
}

private struct RhwpIngest: Encodable {
    let version = "1"
    let defaultFont = "AppleMyungjo"
    let questions: [RhwpQuestion]

    enum CodingKeys: String, CodingKey {
        case version
        case defaultFont = "default_font"
        case questions
    }
}

private struct RhwpQuestion: Encodable {
    let number: Int
    let stem: String
    let choices: [String]
    let autoNumber = false

    enum CodingKeys: String, CodingKey {
        case number
        case stem
        case choices
        case autoNumber = "auto_number"
    }
}

private struct RhwpExtractReceipt: Decodable {
    let pages: [RhwpExtractPage]
}

private struct RhwpExtractPage: Decodable {
    let text: String
}

struct RhwpExportAdapter {
    private static let expectedEngineSHA256 = "a9fc072e61aa1cbf56fbd00943c4e4a33dd49aa7f6122f7b36e16ff476f7677b"
    private let fileManager: FileManager

    init(fileManager: FileManager = .default) {
        self.fileManager = fileManager
    }

    func export(
        project: DocumentProject,
        format: DocumentFormat,
        workingDirectory: URL
    ) throws -> Data {
        let engine = try executable()
        let work = workingDirectory.appendingPathComponent(".rhwp-\(UUID().uuidString)", isDirectory: true)
        try fileManager.createDirectory(at: work, withIntermediateDirectories: false)
        defer { try? fileManager.removeItem(at: work) }
        let ingest = work.appendingPathComponent("document.json")
        let hwpx = work.appendingPathComponent("document.hwpx")
        let hwp = work.appendingPathComponent("document.hwp")
        let questions = project.elements.sorted(by: { $0.order < $1.order }).enumerated().map {
            RhwpQuestion(number: $0.offset + 1, stem: $0.element.text, choices: [])
        }
        try JSONEncoder().encode(RhwpIngest(questions: questions)).write(to: ingest)
        _ = try run(engine, ["build-from-ingest", ingest.path, "-o", hwpx.path])
        try RhwpStyleCompile.apply(to: hwpx, work: work)
        try RhwpTableCompile.apply(to: hwpx, project: project, work: work)
        try embedStyleBinding(in: hwpx, work: work)
        switch format {
        case .hwpx:
            return try Data(contentsOf: hwpx)
        case .hwp:
            _ = try run(engine, ["convert", hwpx.path, hwp.path, "--verify", "--verify-pages"])
            return try Data(contentsOf: hwp)
        case .docx, .markdown:
            throw ExportError.invalidPackage("rhwp adapter received \(format.rawValue)")
        }
    }

    func validate(
        data: Data,
        format: DocumentFormat,
        project: DocumentProject
    ) throws -> [ValidatedExportElement] {
        switch format {
        case .hwpx:
            guard data.starts(with: Data([0x50, 0x4b, 0x03, 0x04])) else {
                throw ExportError.invalidPackage("HWPX ZIP signature")
            }
        case .hwp:
            guard data.starts(with: Data([0xd0, 0xcf, 0x11, 0xe0, 0xa1, 0xb1, 0x1a, 0xe1])) else {
                throw ExportError.invalidPackage("HWP CFB signature")
            }
        case .docx, .markdown:
            throw ExportError.invalidPackage("rhwp adapter received \(format.rawValue)")
        }

        let engine = try executable()
        let document = fileManager.temporaryDirectory
            .appendingPathComponent("public-document-rhwp-validate-\(UUID().uuidString)")
            .appendingPathExtension(format.fileExtension)
        try data.write(to: document, options: .withoutOverwriting)
        defer { try? fileManager.removeItem(at: document) }
        let output = try run(engine, ["export-text", document.path, "--json"])
        let receipt = try JSONDecoder().decode(RhwpExtractReceipt.self, from: output)
        let extracted = receipt.pages.map(\.text).joined(separator: "\n")
        var cursor = extracted.startIndex
        var observed: [ValidatedExportElement] = []
        for element in project.elements.sorted(by: { $0.order < $1.order }) {
            if ["table", "approval-grid"].contains(element.kind), !element.contentHTML.isEmpty {
                let rows = try ExportSerializers.tableRows(element)
                let cells = rows.flatMap { $0 }
                    .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
                    .filter { !$0.isEmpty }
                var searchFrom = cursor
                for cell in cells {
                    guard let range = extracted.range(
                        of: cell,
                        options: .literal,
                        range: searchFrom..<extracted.endIndex
                    ) else {
                        throw ExportError.rhwpFailed(
                            "추출 검증에서 \(element.elementID) 표 셀의 순서 또는 개수가 다릅니다"
                        )
                    }
                    searchFrom = range.upperBound
                }
                observed.append(ValidatedExportElement(
                    elementID: element.elementID,
                    kind: element.kind,
                    order: element.order,
                    textHash: textHash(cells.joined(separator: " "))
                ))
                cursor = searchFrom
                continue
            }
            guard
                !element.text.isEmpty,
                let range = extracted.range(
                    of: element.text,
                    options: .literal,
                    range: cursor..<extracted.endIndex
                )
            else {
                throw ExportError.rhwpFailed(
                    "추출 검증에서 \(element.elementID) 텍스트의 순서 또는 개수가 다릅니다"
                )
            }
            let observedText = String(extracted[range])
            observed.append(ValidatedExportElement(
                elementID: element.elementID,
                kind: element.kind,
                order: element.order,
                textHash: textHash(observedText)
            ))
            cursor = range.upperBound
        }
        return observed
    }

    private func embedStyleBinding(in hwpx: URL, work: URL) throws {
        let memberDirectory = work.appendingPathComponent("PublicDocument", isDirectory: true)
        try fileManager.createDirectory(at: memberDirectory, withIntermediateDirectories: true)
        let member = memberDirectory.appendingPathComponent("style-binding.json")
        try OfficialStyleBinding.json().write(to: member, options: [.atomic])
        let process = Process()
        let standardError = Pipe()
        process.currentDirectoryURL = work
        process.executableURL = URL(fileURLWithPath: "/usr/bin/zip")
        process.arguments = ["-q", "-u", hwpx.lastPathComponent, "PublicDocument/style-binding.json"]
        process.standardOutput = Pipe()
        process.standardError = standardError
        try process.run()
        process.waitUntilExit()
        guard process.terminationStatus == 0 else {
            let diagnostic = String(data: standardError.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
            throw ExportError.rhwpFailed(diagnostic)
        }
    }

    private func textHash(_ text: String) -> String {
        "sha256:" + SHA256.hash(data: Data(text.utf8))
            .map { String(format: "%02x", $0) }
            .joined()
    }

    private func run(_ engine: URL, _ arguments: [String]) throws -> Data {
        let process = Process()
        let standardOutput = Pipe()
        let diagnosticURL = fileManager.temporaryDirectory
            .appendingPathComponent("public-document-rhwp-\(UUID().uuidString).log")
        fileManager.createFile(atPath: diagnosticURL.path, contents: nil)
        let standardError = try FileHandle(forWritingTo: diagnosticURL)
        defer {
            try? standardError.close()
            try? fileManager.removeItem(at: diagnosticURL)
        }
        process.executableURL = engine
        process.arguments = arguments
        process.standardOutput = standardOutput
        process.standardError = standardError
        try process.run()
        let output = standardOutput.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        try standardError.synchronize()
        let diagnosticData = try Data(contentsOf: diagnosticURL)
        let diagnostic = String(data: diagnosticData, encoding: .utf8) ?? ""
        guard process.terminationStatus == 0 else { throw ExportError.rhwpFailed(diagnostic) }
        return output
    }

    private func executable() throws -> URL {
        let bundled = Bundle.main.resourceURL?.appendingPathComponent("Engines/rhwp")
        let source = URL(fileURLWithPath: fileManager.currentDirectoryPath)
            .appendingPathComponent("Resources/Engines/rhwp")
        for candidate in [bundled, source].compactMap({ $0 }) {
            guard fileManager.isExecutableFile(atPath: candidate.path),
                  let data = try? Data(contentsOf: candidate)
            else { continue }
            let digest = SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
            if digest == Self.expectedEngineSHA256 { return candidate }
        }
        throw ExportError.rhwpFailed("고정된 rhwp 엔진이 없거나 승인 해시와 다릅니다")
    }
}
