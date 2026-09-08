from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[1]


def test_docx_and_markdown_preserve_authored_paragraph_whitespace(
    tmp_path: Path,
) -> None:
    authored = "alpha  beta\ngamma\tdelta"
    elements = [
        {
            "elementID": "element-title",
            "kind": "heading",
            "order": 0,
            "text": "Whitespace",
            "contentHTML": "Whitespace",
            "inlineIDs": [],
            "styleID": "style-title",
            "evidenceIDs": [],
        },
        {
            "elementID": "element-body",
            "kind": "paragraph",
            "order": 1,
            "text": authored,
            "contentHTML": authored,
            "inlineIDs": [],
            "styleID": "style-body",
            "evidenceIDs": [],
        },
    ]
    project = {
        "schemaVersion": 1,
        "documentID": "document-whitespace",
        "locale": "ko-KR",
        "title": "Whitespace",
        "currentRevisionID": "revision-1",
        "elements": elements,
        "assets": [],
        "styles": [],
        "templateBinding": {
            "templateID": "public-draft",
            "version": "1.0",
            "publishingAuthority": "test",
            "requiredSections": ["본문"],
            "checklistResults": {},
        },
        "evidenceLinks": [],
        "revisions": [{
            "revisionID": "revision-1",
            "createdAt": "2026-08-31T00:00:00Z",
            "summary": "whitespace",
            "elementIDs": [element["elementID"] for element in elements],
        }],
        "history": [],
        "aiProposalHistory": [],
        "providerConfigurations": [],
        "consentGrants": [],
        "redoRevisionIDs": [],
    }
    source = tmp_path / "project.json"
    destination = tmp_path / "out"
    source.write_text(json.dumps(project), encoding="utf-8")
    destination.mkdir()

    result = subprocess.run(
        [
            str(ROOT / ".build" / "debug" / "PublicDocumentApp"),
            "--export-project",
            str(source),
            str(destination),
            "--formats",
            "docx,markdown",
            "--flattening-consent",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=90,
    )

    assert result.returncode == 0, result.stderr
    receipt = json.loads(result.stdout)
    assert set(receipt["publishedFormats"]) == {"docx", "markdown"}
    assert all(item["semanticValid"] for item in receipt["results"])
    markdown = next(destination.glob("*.md")).read_text(encoding="utf-8")
    assert authored in markdown
    docx = next(destination.glob("*.docx"))
    with zipfile.ZipFile(docx) as package:
        document = package.read("word/document.xml").decode("utf-8")
        manifest = package.read("customXml/item1.xml").decode("utf-8")
    assert "alpha  beta" in document
    assert authored in document
    expected_hash = hashlib.sha256(authored.encode("utf-8")).hexdigest()
    assert f'text-hash="sha256:{expected_hash}"' in manifest
