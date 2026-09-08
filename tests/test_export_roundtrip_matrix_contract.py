from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "qa" / "export-roundtrip-matrix.py"
RICH = ROOT / "tests" / "fixtures" / "official-rich-project.json"
ADVERSARIAL = ROOT / "tests" / "fixtures" / "adversarial-unsupported-project.json"
CAPABILITIES = ROOT / "Resources" / "Capabilities" / "format-capabilities-1.0.0.json"


def _run(fixture: Path, outdir: Path) -> dict:
    result = subprocess.run(
        [
            "python3",
            str(SCRIPT),
            "--fixture",
            str(fixture),
            "--outdir",
            str(outdir),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    output = outdir / ("result.json" if fixture == ADVERSARIAL else "matrix.json")
    return json.loads(output.read_text(encoding="utf-8"))


def test_roundtrip_matrix_proves_every_declared_disposition(tmp_path: Path) -> None:
    outdir = tmp_path / "matrix"
    matrix = _run(RICH, outdir)
    assert matrix["status"] == "pass"
    assert matrix["formats"] == ["hwpx", "hwp", "docx", "markdown"]
    assert matrix["mismatches"] == []
    assert matrix["caseCount"] >= 8
    assert all(case["status"] == "pass" for case in matrix["cases"])
    assert "## swift build" in (outdir / "transcript.txt").read_text(encoding="utf-8")


def test_adversarial_semantic_loss_never_overwrites_existing_files(tmp_path: Path) -> None:
    outdir = tmp_path / "adversarial"
    result = _run(ADVERSARIAL, outdir)
    assert result["status"] == "pass"
    assert result["blockedFormats"] == ["hwpx", "hwp", "docx", "markdown"]
    assert result["changedDestinations"] == []
    assert set(result["semanticLossCapabilities"]) >= {
        "list-item",
        "unordered-list",
    }
    assert "## swift build" in (outdir / "transcript.txt").read_text(encoding="utf-8")


def test_required_semantic_loss_rows_stay_closed_until_roundtrip_proof() -> None:
    resource = json.loads(CAPABILITIES.read_text(encoding="utf-8"))
    rows = {row["capability"]: row for row in resource["matrix"]}

    assert rows["table"]["hwpx"] == rows["table"]["hwp"] == "semantic-loss"
    assert rows["approval-grid"]["hwpx"] == rows["approval-grid"]["hwp"] == "semantic-loss"
    assert rows["formula"]["hwpx"] == rows["formula"]["hwp"] == "semantic-loss"
    assert rows["formula"]["markdown"] == "semantic-loss"
    assert set(rows["list-item"].values()) == {
        "list-item",
        "semantic-loss",
    }
    assert set(rows["unordered-list"].values()) == {
        "unordered-list",
        "semantic-loss",
    }
