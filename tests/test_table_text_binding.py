from __future__ import annotations

import json
import hashlib
import subprocess
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "Resources" / "Studio" / "easy-tools.js"
STUDIO = ROOT / "Resources" / "Studio"


def _eval(expression: str):
    script = f"""
    const fs = require('fs');
    const vm = require('vm');
    const sandbox = {{ console, PublicDocumentEasyTools: undefined }};
    sandbox.globalThis = sandbox;
    vm.runInNewContext(fs.readFileSync({json.dumps(str(TOOLS))}, 'utf8'), sandbox);
    const tools = sandbox.PublicDocumentEasyTools;
    const value = {expression};
    process.stdout.write(JSON.stringify(value));
    """
    result = subprocess.run(
        ["node", "--input-type=commonjs", "-e", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_bind_table_text_joins_cells_like_docx_body_binding() -> None:
    html = (
        '<table data-easy-table="true"><tbody>'
        "<tr><td>평가영역</td><td>주요 지표</td></tr>"
        "<tr><td>교육</td><td>이수율, 이해도</td></tr>"
        "</tbody></table>"
    )
    bound = _eval(
        "tools.bindTableText("
        f"{{kind:'table', text:'평가영역주요 지표', contentHTML:{json.dumps(html)}}})"
    )
    assert bound["text"] == "평가영역 주요 지표 교육 이수율, 이해도"
    assert bound["kind"] == "table"
    assert _eval("tools.bindTableText({kind:'paragraph', text:'본문', contentHTML:'본문'})")["text"] == "본문"


def test_studio_binds_table_text_on_commit_and_editor_snapshot() -> None:
    library = (STUDIO / "easy-library.js").read_text(encoding="utf-8")
    content = (STUDIO / "project-content.js").read_text(encoding="utf-8")
    export = (ROOT / "Sources/PublicDocumentApp/DocumentExport.swift").read_text(encoding="utf-8")
    serializers = (ROOT / "Sources/PublicDocumentApp/ExportSerializers.swift").read_text(encoding="utf-8")

    assert "bindTableText" in library
    assert "bindTableText" in content
    assert "bindTableText" in export
    assert "func bindTableText" in serializers
    assert "OfficialLayoutEngine.compile" in serializers


def test_docx_export_binds_stale_table_text_to_cells(tmp_path: Path) -> None:
    html = (
        '<table data-easy-table="true"><tbody>'
        "<tr><td>평가영역</td><td>주요 지표</td></tr>"
        "<tr><td>교육</td><td>이수율</td></tr>"
        "</tbody></table>"
    )
    project = {
        "schemaVersion": 1,
        "documentID": "document-table-bind",
        "locale": "ko-KR",
        "title": "표 바인딩",
        "currentRevisionID": "revision-1",
        "elements": [
            {
                "elementID": "element-title",
                "kind": "heading",
                "order": 0,
                "text": "표 바인딩",
                "contentHTML": "표 바인딩",
                "inlineIDs": [],
                "styleID": "style-title",
                "evidenceIDs": [],
            },
            {
                "elementID": "element-table-indicators",
                "kind": "table",
                "order": 1,
                "text": "평가영역주요 지표교육이수율",
                "contentHTML": html,
                "inlineIDs": [],
                "styleID": "style-table",
                "evidenceIDs": [],
            },
        ],
        "assets": [],
        "styles": [],
        "templateBinding": {
            "templateID": "public-draft",
            "version": "1.0",
            "publishingAuthority": "기관 표준",
            "requiredSections": ["본문"],
            "checklistResults": {},
        },
        "evidenceLinks": [],
        "revisions": [
            {
                "revisionID": "revision-1",
                "createdAt": "2026-08-28T09:00:00Z",
                "summary": "table-bind",
                "elementIDs": ["element-title", "element-table-indicators"],
            }
        ],
        "history": [],
        "aiProposalHistory": [],
        "providerConfigurations": [],
        "consentGrants": [],
        "redoRevisionIDs": [],
    }
    source = tmp_path / "project.json"
    destination = tmp_path / "out"
    destination.mkdir()
    source.write_text(json.dumps(project, ensure_ascii=False), encoding="utf-8")
    binary = ROOT / ".build" / "debug" / "PublicDocumentApp"
    result = subprocess.run(
        [str(binary), "--export-project", str(source), str(destination), "--formats", "docx", "--flattening-consent"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stderr
    receipt = json.loads(result.stdout)
    assert receipt.get("failedFormats") in (None, [])
    assert "docx" in (receipt.get("publishedFormats") or [])
    assert any(item.get("format") == "docx" for item in receipt.get("results") or [])
    artifacts = list(destination.glob("*.docx"))
    assert len(artifacts) == 1
    with zipfile.ZipFile(artifacts[0]) as package:
        manifest = package.read("customXml/item1.xml").decode("utf-8")
    bound_hash = hashlib.sha256(
        "평가영역 주요 지표 교육 이수율".encode("utf-8")
    ).hexdigest()
    stale_hash = hashlib.sha256(
        "평가영역주요 지표교육이수율".encode("utf-8")
    ).hexdigest()
    assert f'text-hash="sha256:{bound_hash}"' in manifest
    assert f'text-hash="sha256:{stale_hash}"' not in manifest


def test_docx_export_splits_official_lines_with_hanging_indent(tmp_path: Path) -> None:
    import zipfile
    from xml.etree import ElementTree

    project = {
        "schemaVersion": 1,
        "documentID": "document-official-lines",
        "locale": "ko-KR",
        "title": "조판",
        "currentRevisionID": "revision-1",
        "elements": [
            {
                "elementID": "element-title",
                "kind": "heading",
                "order": 0,
                "text": "조판",
                "contentHTML": "조판",
                "inlineIDs": [],
                "styleID": "style-title",
                "evidenceIDs": [],
            },
            {
                "elementID": "element-body",
                "kind": "paragraph",
                "order": 1,
                "text": "○ 첫 항목. ○ 둘째 함. 1. 표준 - 세부",
                "contentHTML": "○ 첫 항목. ○ 둘째 함. 1. 표준 - 세부",
                "inlineIDs": [],
                "styleID": "style-body",
                "evidenceIDs": [],
            },
        ],
        "assets": [],
        "styles": [],
        "templateBinding": {
            "templateID": "public-draft",
            "version": "1.0",
            "publishingAuthority": "기관 표준",
            "requiredSections": ["본문"],
            "checklistResults": {},
        },
        "evidenceLinks": [],
        "revisions": [
            {
                "revisionID": "revision-1",
                "createdAt": "2026-08-28T09:00:00Z",
                "summary": "lines",
                "elementIDs": ["element-title", "element-body"],
            }
        ],
        "history": [],
        "aiProposalHistory": [],
        "providerConfigurations": [],
        "consentGrants": [],
        "redoRevisionIDs": [],
    }
    source = tmp_path / "project.json"
    destination = tmp_path / "out"
    destination.mkdir()
    source.write_text(json.dumps(project, ensure_ascii=False), encoding="utf-8")
    binary = ROOT / ".build" / "debug" / "PublicDocumentApp"
    result = subprocess.run(
        [str(binary), "--export-project", str(source), str(destination), "--formats", "docx", "--flattening-consent"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stderr
    receipt = json.loads(result.stdout)
    assert "docx" in (receipt.get("publishedFormats") or [])
    docx = next(destination.glob("*.docx"))
    with zipfile.ZipFile(docx) as package:
        xml = package.read("word/document.xml")
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    root = ElementTree.fromstring(xml)
    body = None
    for sdt in root.findall(".//w:sdt", ns):
        tag = sdt.find(".//w:tag", ns)
        if tag is not None and tag.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val") == "element-body":
            body = sdt
            break
    assert body is not None
    paragraphs = body.findall(".//w:p", ns)
    texts = ["".join(node.text or "" for node in paragraph.findall(".//w:t", ns)) for paragraph in paragraphs]
    assert len(paragraphs) >= 4
    assert texts[0].startswith("○ 첫")
    assert any(text.startswith("○ 둘째") for text in texts)
    assert any(text.startswith("1. 표준") for text in texts)
    assert any(text.startswith("- 세부") for text in texts)
    assert any(paragraph.find(".//w:ind", ns) is not None for paragraph in paragraphs)


def test_docx_compiles_official_margin_hierarchy_and_keeps_attachment(tmp_path: Path) -> None:
    import zipfile
    from xml.etree import ElementTree

    project = {
        "schemaVersion": 1,
        "documentID": "document-official-compile",
        "locale": "ko-KR",
        "title": "조판계층",
        "currentRevisionID": "revision-1",
        "elements": [
            {
                "elementID": "element-title",
                "kind": "heading",
                "order": 0,
                "text": "조판계층",
                "contentHTML": "조판계층",
                "inlineIDs": [],
                "styleID": "style-title",
                "evidenceIDs": [],
            },
            {
                "elementID": "element-body",
                "kind": "paragraph",
                "order": 1,
                "text": "1. 상위 ○ 본문 가. 하위 - 세부 가. 붙임 1. 성과지표 표. 끝.",
                "contentHTML": "1. 상위 ○ 본문 가. 하위 - 세부 가. 붙임 1. 성과지표 표. 끝.",
                "inlineIDs": [],
                "styleID": "style-body",
                "evidenceIDs": [],
            },
            {
                "elementID": "element-table-indicators",
                "kind": "table",
                "order": 2,
                "text": "평가영역 주요 지표",
                "contentHTML": (
                    '<table data-easy-table="true"><tbody>'
                    "<tr><td>평가영역</td><td>주요 지표</td></tr>"
                    "<tr><td>교육</td><td>이수율</td></tr>"
                    "</tbody></table>"
                ),
                "inlineIDs": [],
                "styleID": "style-table",
                "evidenceIDs": [],
            },
        ],
        "assets": [],
        "styles": [],
        "templateBinding": {
            "templateID": "public-draft",
            "version": "1.0",
            "publishingAuthority": "기관 표준",
            "requiredSections": ["본문"],
            "checklistResults": {},
        },
        "evidenceLinks": [],
        "revisions": [
            {
                "revisionID": "revision-1",
                "createdAt": "2026-08-28T09:00:00Z",
                "summary": "compile",
                "elementIDs": ["element-title", "element-body", "element-table-indicators"],
            }
        ],
        "history": [],
        "aiProposalHistory": [],
        "providerConfigurations": [],
        "consentGrants": [],
        "redoRevisionIDs": [],
    }
    source = tmp_path / "project.json"
    destination = tmp_path / "out"
    destination.mkdir()
    source.write_text(json.dumps(project, ensure_ascii=False), encoding="utf-8")
    binary = ROOT / ".build" / "debug" / "PublicDocumentApp"
    result = subprocess.run(
        [str(binary), "--export-project", str(source), str(destination), "--formats", "docx", "--flattening-consent"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stderr
    docx = next(destination.glob("*.docx"))
    with zipfile.ZipFile(docx) as package:
        xml = package.read("word/document.xml")
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    root = ElementTree.fromstring(xml)
    sect = root.find(".//w:pgMar", ns)
    assert sect is not None
    assert sect.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}top") == "1134"
    assert sect.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}bottom") == "567"
    body = None
    for sdt in root.findall(".//w:sdt", ns):
        tag = sdt.find(".//w:tag", ns)
        if tag is not None and tag.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val") == "element-body":
            body = sdt
            break
    assert body is not None
    paragraphs = body.findall(".//w:p", ns)
    texts = ["".join(node.text or "" for node in paragraph.findall(".//w:t", ns)) for paragraph in paragraphs]
    assert any(text.startswith("1. 상위") for text in texts)
    assert any(text.startswith("○ 본문") for text in texts)
    assert any("붙임 1. 성과지표" in text for text in texts)
    assert not any(text == "1. 성과지표 표. 끝." for text in texts)
    def indent_of(prefix: str):
        for paragraph, text in zip(paragraphs, texts):
            if text.startswith(prefix):
                ind = paragraph.find(".//w:ind", ns)
                assert ind is not None, prefix
                left = ind.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}left")
                hanging = ind.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}hanging")
                assert left is not None and hanging is not None, prefix
                return int(left), int(hanging)
        raise AssertionError(prefix)
    one_left, one_hang = indent_of("1. 상위")
    ga_left, ga_hang = indent_of("가. 하위")
    assert one_left == one_hang
    assert ga_left - ga_hang > 0
    assert ga_left > one_left
    fills = [
        node.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}fill")
        for node in root.findall(".//w:shd", ns)
    ]
    assert "F4F4F5" in fills
