from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "scripts" / "verify-genoffice-docx-reopen.mjs"


def test_genoffice_reopen_tool_rejects_an_existing_output_root(tmp_path: Path) -> None:
    # Given: an output directory that already contains prior evidence.
    output_root = tmp_path / "existing-evidence"
    output_root.mkdir()

    # When: the verifier is asked to write into that directory.
    result = subprocess.run(
        [
            "node",
            str(TOOL),
            "--genoffice-root",
            str(tmp_path / "missing-genoffice"),
            "--artifact",
            str(tmp_path / "missing.docx"),
            "--fixture",
            str(tmp_path / "missing.json"),
            "--output-root",
            str(output_root),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    # Then: evidence is never overwritten and launch is never attempted.
    assert result.returncode != 0
    assert "output root already exists" in result.stderr
    assert list(output_root.iterdir()) == []


def test_genoffice_reopen_tool_requires_every_boundary_input(tmp_path: Path) -> None:
    # Given: only the pinned client root is supplied.
    # When: the verifier parses the incomplete boundary.
    result = subprocess.run(
        [
            "node",
            str(TOOL),
            "--genoffice-root",
            str(tmp_path / "genoffice"),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    # Then: the missing artifact boundary is reported before any launch.
    assert result.returncode != 0
    assert "missing required option: --artifact" in result.stderr
