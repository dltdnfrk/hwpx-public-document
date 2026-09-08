from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "Sources" / "PublicDocumentApp"


def test_rhwp_export_compiles_simple_tables_into_owpml() -> None:
    compile_source = (SOURCES / "RhwpTableCompile.swift").read_text(encoding="utf-8")
    export_source = (SOURCES / "RhwpExport.swift").read_text(encoding="utf-8")
    style_source = (SOURCES / "RhwpStyleCompile.swift").read_text(encoding="utf-8")
    matrix = json.loads(
        (ROOT / "Resources" / "Capabilities" / "format-capabilities-1.0.0.json").read_text(
            encoding="utf-8"
        )
    )
    table = next(row for row in matrix["matrix"] if row["capability"] == "table")

    assert "enum RhwpTableCompile" in compile_source
    assert "hp:tbl" in compile_source
    assert "hp:tc" in compile_source
    assert "ExportSerializers.tableRows" in compile_source
    assert "approval-grid" in compile_source
    assert "borderFillIDRef=" in compile_source
    assert 'borderFillIDRef=\\"2\\"' in compile_source
    assert "RhwpTableCompile.apply" in export_source
    assert export_source.index("RhwpTableCompile.apply") < export_source.index("RhwpStyleCompile.apply")
    assert 'body.contains("<hp:tbl")' in style_source
    assert "tableRows" in export_source
    assert "textHash(normalizedText(cells.joined(separator: \" \")))" in export_source
    assert "textHash(normalizedText(String(extracted[range])))" in export_source
    assert "law.go.kr" not in compile_source
    assert table["hwpx"] == "semantic-loss"


def test_rhwp_table_survives_style_compile_and_duplicate_body_is_not_title(
    tmp_path: Path,
) -> None:
    project = {
        "schemaVersion": 1,
        "documentID": "document-rhwp-table-style",
        "locale": "ko-KR",
        "title": "Same",
        "currentRevisionID": "revision-1",
        "elements": [
            {
                "elementID": "element-title",
                "kind": "heading",
                "order": 0,
                "text": "Same",
                "contentHTML": "Same",
                "inlineIDs": [],
                "styleID": "style-title",
                "evidenceIDs": [],
            },
            {
                "elementID": "element-body",
                "kind": "paragraph",
                "order": 1,
                "text": "Same",
                "contentHTML": "Same",
                "inlineIDs": [],
                "styleID": "style-body",
                "evidenceIDs": [],
            },
            {
                "elementID": "element-table",
                "kind": "table",
                "order": 2,
                "text": "구분 값 교육 95",
                "contentHTML": (
                    '<table data-easy-table="true"><tbody>'
                    "<tr><th>구분</th><th>값</th></tr>"
                    "<tr><td>교육</td><td>95</td></tr>"
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
        "revisions": [{
            "revisionID": "revision-1",
            "createdAt": "2026-08-28T09:00:00Z",
            "summary": "rhwp-table-style",
            "elementIDs": ["element-title", "element-body", "element-table"],
        }],
        "history": [],
        "aiProposalHistory": [],
        "providerConfigurations": [],
        "consentGrants": [],
        "redoRevisionIDs": [],
    }
    source = tmp_path / "project.json"
    artifact = tmp_path / "compiled.hwpx"
    source.write_text(json.dumps(project, ensure_ascii=False), encoding="utf-8")
    binary = ROOT / ".build" / "debug" / "PublicDocumentApp"
    result = subprocess.run(
        [
            str(binary),
            "--rhwp-compile-self-test",
            str(source),
            str(artifact),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=90,
    )

    assert result.returncode == 0, result.stderr
    with zipfile.ZipFile(artifact) as package:
        section = package.read("Contents/section0.xml").decode("utf-8")
    same_styles = []
    for paragraph in re.findall(r"<hp:p\b[^>]*>[\s\S]*?</hp:p>", section):
        if "<hp:t>Same</hp:t>" not in paragraph:
            continue
        opening = paragraph[:paragraph.index(">")]
        style = re.search(
            r'paraPrIDRef="(\d+)" styleIDRef="(\d+)"',
            opening,
        )
        assert style is not None
        same_styles.append(style.groups())
    assert same_styles[:2] == [("2", "1"), ("0", "3")]
    assert "<hp:tbl" in section
    assert section.count("<hp:tc") == 4
    extracted = subprocess.run(
        [
            str(ROOT / "Resources" / "Engines" / "rhwp"),
            "export-text",
            str(artifact),
            "--json",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    text = "\n".join(page["text"] for page in json.loads(extracted.stdout)["pages"])
    assert all(cell in text for cell in ("구분", "값", "교육", "95"))
