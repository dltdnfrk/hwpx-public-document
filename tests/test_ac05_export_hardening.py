from __future__ import annotations

import json
import subprocess
import zipfile
from functools import lru_cache
from pathlib import Path
from typing import TypedDict, cast
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[1]


class OrderedElementReceipt(TypedDict):
    elementID: str
    kind: str
    order: int


class ValidationReceipt(TypedDict):
    structuralValid: bool
    semanticValid: bool
    evidenceSource: str
    orderedElements: list[OrderedElementReceipt]


class ExportResultReceipt(TypedDict):
    fileName: str
    relativePath: str
    validation: ValidationReceipt


class LossReportReceipt(TypedDict):
    format: str
    capability: str
    elementID: str
    elementPath: str
    classification: str
    evidenceSource: str


class ExportReceipt(TypedDict):
    results: list[ExportResultReceipt]
    lossReports: list[LossReportReceipt]
    publishedFormats: list[str]


@lru_cache(maxsize=1)
def _app_binary() -> Path:
    _ = subprocess.run(
        ["swift", "build"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return ROOT / ".build" / "debug" / "PublicDocumentApp"


def _export(tmp_path: Path, scenario: str) -> tuple[Path, ExportReceipt]:
    destination = tmp_path / scenario
    result = subprocess.run(
        [str(_app_binary()), "--export-self-test", str(destination), scenario],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    receipt = cast(ExportReceipt, json.loads(result.stdout))
    return destination, receipt


def _run_swift_harness(
    tmp_path: Path,
    source: str,
    source_files: tuple[str, ...],
    *arguments: str,
) -> subprocess.CompletedProcess[str]:
    runner = tmp_path / "main.swift"
    _ = runner.write_text(source, encoding="utf-8")
    binary = tmp_path / "ac05-swift-harness"
    _ = subprocess.run(
        [
            "swiftc",
            *(str(ROOT / "Sources" / "PublicDocumentApp" / name) for name in source_files),
            str(runner),
            "-o",
            str(binary),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return subprocess.run(
        [str(binary), *arguments],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def test_loss_reports_address_list_items_and_table_rich_trigger(tmp_path: Path) -> None:
    # Given: the frozen authoring-universe fixture contains a two-item list and rich tables.
    fixture = ROOT / "Resources" / "Compatibility" / "Fixtures" / "authoring-universe-project.json"
    result = _run_swift_harness(
        tmp_path,
        """
import Foundation

struct FormatValidationReceipt: Codable {}

let project = try JSONDecoder().decode(
    DocumentProject.self,
    from: Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1]))
)
let reports = try FormatCapabilityPolicy.lossReports(project: project, format: .hwpx)
    .filter { $0.classification == .semanticLoss }
let encoder = JSONEncoder()
encoder.outputFormatting = [.sortedKeys]
FileHandle.standardOutput.write(try encoder.encode(reports))
""",
        (
            "AIGovernance.swift",
            "AIGovernanceModels.swift",
            "AIGovernanceProposalEngine.swift",
            "AIGovernanceRevisionEngine.swift",
            "DocumentProject.swift",
            "DocumentProjectCoreModels.swift",
            "DocumentProjectAIModels.swift",
            "DocumentProjectState.swift",
            "DocumentProjectStore.swift",
            "ExportModel.swift",
            "CompatibilityEvidence.swift",
            "FormatCapabilityPolicy.swift",
            "FormatCapabilityObservation.swift",
            "FormatCapabilityReporting.swift",
        ),
        str(fixture),
    )
    reports = json.loads(result.stdout)

    # When: semantic preflight diagnostics are projected to machine-readable paths.
    list_reports = [
        (report["capability"], report["elementPath"])
        for report in reports
        if report["elementID"] == "element-unordered-list"
        and report["capability"] in {"unordered-list", "list-item"}
    ]
    table_reports = [
        report
        for report in reports
        if report["capability"] == "table+rich-inline"
    ]

    # Then: the list container and every item are distinct, and rich-table paths are concrete.
    assert list_reports == [
        ("list-item", "elements/3"),
        ("unordered-list", "elements/3/lists/0"),
        ("list-item", "elements/3/lists/0/items/0"),
        ("list-item", "elements/3/lists/0/items/1"),
    ]
    assert {report["elementID"]: report["elementPath"] for report in table_reports} == {
        "element-table": "elements/4/table/inlines/inline-table-strong",
    }


def test_genoffice_list_item_and_css_fonts_have_precise_governed_losses(
    tmp_path: Path,
) -> None:
    # Given: the exact block kind and CSS font markup emitted by the GenOffice editor.
    result = _run_swift_harness(
        tmp_path,
        """
import Foundation

struct FormatValidationReceipt: Codable {}

let element = DocumentElement(
    elementID: "element-genoffice-list-item",
    kind: "list-item",
    order: 4,
    text: "첫 번째 항목",
    contentHTML: #"<span data-public-document-align="center"><span style="font-family: &quot;serif&quot;; font-size: 14pt"><strong data-inline-id="inline-alpha"><em data-inline-id="inline-bravo"><u data-inline-id="inline-charlie">첫 번째 항목</u></em></strong></span></span>"#,
    inlineIDs: ["inline-alpha", "inline-bravo", "inline-charlie"],
    styleID: "style-body",
    evidenceIDs: []
)
let revision = DocumentRevision(
    revisionID: "revision-genoffice-list-item",
    createdAt: "2026-08-10T00:00:00Z",
    summary: "GenOffice list item capability fixture",
    elementIDs: [element.elementID],
    snapshotElements: [element]
)
let project = DocumentProject(
    schemaVersion: 1, documentID: "document-genoffice-list-item", locale: "ko-KR",
    title: "목록 기능 표본", currentRevisionID: revision.revisionID,
    elements: [element], assets: [],
    styles: [DocumentStyle(styleID: "style-body", name: "본문", properties: [:])],
    templateBinding: ProjectTemplateBinding(
        templateID: "capability-fixture", version: "1.0.0", publishingAuthority: "test",
        requiredSections: [], checklistResults: [:]
    ),
    evidenceLinks: [], revisions: [revision], history: [], aiProposalHistory: []
)
let reports = try FormatCapabilityPolicy.lossReports(project: project, format: .docx)
let encoder = JSONEncoder()
encoder.outputFormatting = [.sortedKeys]
FileHandle.standardOutput.write(try encoder.encode(reports))
""",
        (
            "AIGovernance.swift",
            "AIGovernanceModels.swift",
            "AIGovernanceProposalEngine.swift",
            "AIGovernanceRevisionEngine.swift",
            "DocumentProject.swift",
            "DocumentProjectCoreModels.swift",
            "DocumentProjectAIModels.swift",
            "DocumentProjectState.swift",
            "DocumentProjectStore.swift",
            "ExportModel.swift",
            "CompatibilityEvidence.swift",
            "FormatCapabilityPolicy.swift",
            "FormatCapabilityObservation.swift",
            "FormatCapabilityReporting.swift",
        ),
    )
    reports = json.loads(result.stdout)
    governed = {
        (report["capability"], report["elementID"], report["elementPath"])
        for report in reports
    }

    # When/Then: preflight accepts the authored list item and reports every CSS/mark loss
    # against the stable source element and nearest stable inline identity.
    assert {
        (
            "list-item",
            "element-genoffice-list-item",
            "elements/4",
        ),
        (
            "strong",
            "element-genoffice-list-item",
            "elements/4/inlines/inline-alpha",
        ),
        (
            "emphasis",
            "element-genoffice-list-item",
            "elements/4/inlines/inline-bravo",
        ),
        (
            "underline",
            "element-genoffice-list-item",
            "elements/4/inlines/inline-charlie",
        ),
        (
            "font-face",
            "element-genoffice-list-item",
            "elements/4/inlines/inline-alpha",
        ),
        (
            "font-size",
            "element-genoffice-list-item",
            "elements/4/inlines/inline-alpha",
        ),
    } <= governed


def test_artifact_validation_rejects_content_mutation_with_intact_markers(
    tmp_path: Path,
) -> None:
    # Given: locally serialized DOCX and Markdown with formula, tables, and rich source text.
    fixture = ROOT / "Resources" / "Compatibility" / "Fixtures" / "authoring-universe-project.json"
    result = _run_swift_harness(
        tmp_path,
        """
import Foundation

func expectRejected(_ label: String, _ operation: () throws -> Void) {
    var rejected = false
    do { try operation() } catch { rejected = true }
    precondition(rejected, label)
}

let project = try JSONDecoder().decode(DocumentProject.self, from: Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1])))
let docxProject = DocumentProject(
    schemaVersion: project.schemaVersion, documentID: project.documentID, locale: project.locale,
    title: project.title, currentRevisionID: project.currentRevisionID,
    elements: project.elements.filter { $0.kind != "list-item" }, assets: project.assets,
    styles: project.styles, templateBinding: project.templateBinding,
    evidenceLinks: project.evidenceLinks, revisions: project.revisions, history: project.history,
    aiProposalHistory: project.aiProposalHistory
)
let markdownProject = DocumentProject(
    schemaVersion: project.schemaVersion, documentID: project.documentID, locale: project.locale,
    title: project.title, currentRevisionID: project.currentRevisionID,
    elements: docxProject.elements.filter { $0.kind != "formula" }, assets: project.assets,
    styles: project.styles, templateBinding: project.templateBinding,
    evidenceLinks: project.evidenceLinks, revisions: project.revisions, history: project.history,
    aiProposalHistory: project.aiProposalHistory
)
let docx = try ExportSerializers.docx(project: docxProject)
let markdown = try ExportSerializers.markdown(project: markdownProject)
_ = try ExportArtifactValidator.validate(data: docx, format: .docx, project: docxProject)
_ = try ExportArtifactValidator.validate(data: markdown, format: .markdown, project: markdownProject)

func mutatedDOCX(_ replacements: [(String, String)]) throws -> Data {
    var parts = try PackageArchive.parts(from: docx)
    var document = String(data: parts["word/document.xml"]!, encoding: .utf8)!
    for replacement in replacements { document = document.replacingOccurrences(of: replacement.0, with: replacement.1) }
    parts["word/document.xml"] = Data(document.utf8)
    return try PackageArchive.data(parts: parts.map { PackagePart(path: $0.key, data: $0.value) })
}
expectRejected("DOCX formula") {
    let mutated = try mutatedDOCX([("<m:oMath>", "<m:oMathPara>"), ("</m:oMath>", "</m:oMathPara>")])
    _ = try ExportArtifactValidator.validate(data: mutated, format: .docx, project: docxProject)
}
expectRejected("DOCX table header") {
    let mutated = try mutatedDOCX([("<w:tblHeader w:val=\\\"true\\\"/>", "")])
    _ = try ExportArtifactValidator.validate(data: mutated, format: .docx, project: docxProject)
}
expectRejected("DOCX rich content") {
    _ = try ExportArtifactValidator.validate(data: try mutatedDOCX([("굵게", "누락")]), format: .docx, project: docxProject)
}
let markdownSource = String(data: markdown, encoding: .utf8)!
for (label, source) in [
    ("Markdown preamble", "```\\n" + markdownSource),
    ("Markdown table", markdownSource.replacingOccurrences(of: "th>", with: "td>")),
    ("Markdown content", markdownSource.replacingOccurrences(of: "굵게 기울임 밑줄 글꼴 문구 묶음", with: "누락")),
] {
    expectRejected(label) {
        _ = try ExportArtifactValidator.validate(data: Data(source.utf8), format: .markdown, project: markdownProject)
    }
}
print("artifact-derived mutation checks: pass")
""",
        (
            "AIGovernance.swift",
            "AIGovernanceModels.swift",
            "AIGovernanceProposalEngine.swift",
            "AIGovernanceRevisionEngine.swift",
            "DocumentProject.swift",
            "DocumentProjectCoreModels.swift",
            "DocumentProjectAIModels.swift",
            "DocumentProjectState.swift",
            "DocumentProjectStore.swift",
            "ExportModel.swift",
            "CompatibilityEvidence.swift",
            "FormatCapabilityPolicy.swift",
            "FormatCapabilityObservation.swift",
            "FormatCapabilityReporting.swift",
            "PackageArchive.swift",
            "PackageArchiveModels.swift",
            "PackageArchiveReader.swift",
            "PackageArchiveWriter.swift",
            "OfficialTypeset.swift",
            "OfficialLayoutEngine.swift",
            "ExportSerializers.swift",
            "ExportValidation.swift",
            "RhwpExport.swift",
            "RhwpLargeTextCompile.swift",
            "RhwpStyleCompile.swift",
            "RhwpTableCompile.swift",
        ),
        str(fixture),
    )

    # When/Then: body mutations fail independently of source-authored sidecar markers.
    assert result.stdout == "artifact-derived mutation checks: pass\n"


def test_docx_has_resolvable_styles_custom_xml_and_table_grid(tmp_path: Path) -> None:
    # Given: the frozen nested fixture with headings, a table, and an approval grid.
    destination, _ = _export(tmp_path, "all-consented")

    # When: the emitted OPC relationship graph and WordprocessingML are inspected.
    with zipfile.ZipFile(destination / "ac05-fixture.docx") as package:
        names = set(package.namelist())
        document = ElementTree.fromstring(package.read("word/document.xml"))
        relationships = ElementTree.fromstring(package.read("word/_rels/document.xml.rels"))

        # Then: referenced styles and stable-ID metadata are real related parts.
        assert "word/styles.xml" in names
        assert "customXml/itemProps1.xml" in names
        relationship_targets = {item.attrib["Target"] for item in relationships}
        assert "styles.xml" in relationship_targets
        assert "../customXml/item1.xml" in relationship_targets
        namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        assert document.findall(".//w:tbl/w:tblGrid", namespace)
        assert document.findall(".//w:tr/w:trPr/w:tblHeader", namespace)


def test_format_receipts_bind_ordered_artifact_elements(tmp_path: Path) -> None:
    # Given: every locally publishable format from one immutable snapshot.
    _, receipt = _export(tmp_path, "all-consented")

    # When/Then: validity is backed by ordered artifact-derived element evidence.
    for result in receipt["results"]:
        validation = result["validation"]
        assert result["relativePath"] == result["fileName"]
        assert validation["structuralValid"] is True
        assert validation["semanticValid"] is True
        assert validation["evidenceSource"] == "artifact-derived"
        assert validation["orderedElements"]
        assert [item["order"] for item in validation["orderedElements"]] == sorted(
            item["order"] for item in validation["orderedElements"]
        )
        assert all(item["elementID"] and item["kind"] for item in validation["orderedElements"])


def test_runtime_matrix_detects_bare_bold_inside_table_fixture(tmp_path: Path) -> None:
    # Given: the approval-grid fixture contains a bare <b> element.
    _, receipt = _export(tmp_path, "all-consented")

    # When: runtime loss policy evaluates DOCX and Markdown.
    matches = {
        (report["format"], report["elementID"], report["capability"], report["classification"])
        for report in receipt["lossReports"]
    }

    # Then: the frozen table+rich-inline matrix row requires explicit flattening consent.
    assert ("docx", "element-approval", "table+rich-inline", "visual-only-flattening") in matches
    assert ("markdown", "element-approval", "table+rich-inline", "visual-only-flattening") in matches


def test_markdown_escapes_authored_markup_and_retains_element_identity(tmp_path: Path) -> None:
    # Given: authored text containing raw HTML and CommonMark delimiters.
    destination, receipt = _export(tmp_path, "adversarial-markdown")

    # When: the artifact is read as CommonMark source.
    markdown = (destination / "ac05-fixture.md").read_text(encoding="utf-8")

    # Then: authored markup is inert and every source element has a stable marker.
    assert receipt["publishedFormats"] == ["markdown"]
    assert "<script>" not in markdown
    assert "&lt;script&gt;" in markdown
    assert "<!-- public-document element-id=" in markdown


def test_export_consent_is_fresh_for_each_dialog_and_retry() -> None:
    # Given: the Studio export dialog and native batch retry store.
    script = "\n".join(p.read_text(encoding="utf-8") for p in sorted((ROOT / "Resources" / "Studio").glob("*.js")))
    store = (ROOT / "Sources" / "PublicDocumentApp" / "BatchExportStore.swift").read_text(
        encoding="utf-8"
    )

    # When/Then: consent is cleared on dialog open/completion and never copied to retry.
    assert "exportConsent.checked = false" in script
    assert "flatteningConsent: []" in store
