from __future__ import annotations

import json
import subprocess
import zipfile
from pathlib import Path
from typing import Final


ROOT: Final = Path(__file__).resolve().parents[1]


def test_docx_export_runs_pinned_genoffice_normalizer_and_preserves_identity(
    tmp_path: Path,
) -> None:
    # Given: the packaged arm64 GenOffice runtime and a Korean DOCX fixture.
    _ = subprocess.run(
        ["swift", "build"], cwd=ROOT, check=True, capture_output=True, text=True
    )
    destination = tmp_path / "genoffice-docx"

    # When: the application exports DOCX through its public self-test surface.
    completed = subprocess.run(
        [
            str(ROOT / ".build" / "debug" / "PublicDocumentApp"),
            "--export-self-test",
            str(destination),
            "mixed-semantic-block",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    receipt = json.loads(completed.stdout)

    # Then: the runtime identity and independent artifact validation bind the output.
    docx_result = next(item for item in receipt["results"] if item["format"] == "docx")
    identity = docx_result["engineIdentity"]
    assert identity["engine"] == "genoffice-docx-normalize"
    assert identity["packageName"] == "@genoffice/docx-engine"
    assert identity["nodeArchitecture"] == "arm64"
    assert identity["cliSHA256"].startswith("sha256:")
    assert identity["nodeSHA256"].startswith("sha256:")
    assert identity["savedAt"] == "2026-08-09T00:00:00Z"
    assert docx_result["validation"]["evidenceSource"] == "artifact-derived"
    artifact = destination / docx_result["fileName"]
    with zipfile.ZipFile(artifact) as package:
        assert "customXml/item1.xml" in package.namelist()
        document = package.read("word/document.xml").decode("utf-8")
        manifest = package.read("customXml/item1.xml").decode("utf-8")
    assert "element-summary-body" in document
    assert "element-summary-body" in manifest
    assert "생활안전" in document
    assert list(destination.glob(".genoffice-*")) == []
