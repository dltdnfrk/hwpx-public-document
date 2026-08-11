from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify-rhwp-visual.mjs"
FIXTURE = (
    ROOT
    / "Resources"
    / "Compatibility"
    / "Fixtures"
    / "basic-text-project.json"
)
ARTIFACT_ROOT = (
    ROOT
    / "output"
    / "ac-07"
    / "final-bound.0njV0d"
    / "basic-client-interoperability"
)
RHWP_SHA256 = "sha256:a9fc072e61aa1cbf56fbd00943c4e4a33dd49aa7f6122f7b36e16ff476f7677b"
EXPECTED_ELEMENT_IDS = ["element-title", "element-body", "element-review"]


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _run(format_name: str, output_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "node",
            str(SCRIPT),
            "--artifact",
            str(ARTIFACT_ROOT / f"ac05-fixture.{format_name}"),
            "--fixture",
            str(FIXTURE),
            "--output-root",
            str(output_root),
            "--format",
            format_name,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=45,
    )


@pytest.mark.parametrize("format_name", ["hwpx", "hwp"])
def test_rhwp_visual_observation_binds_actual_render_evidence(format_name: str) -> None:
    # Given: the canonical HWP-family artifact and frozen authored fixture.
    artifact = ARTIFACT_ROOT / f"ac05-fixture.{format_name}"
    artifact_hash = _sha256(artifact)
    fixture_hash = _sha256(FIXTURE)

    with tempfile.TemporaryDirectory(prefix="rhwp-visual-test-", dir=ROOT / "output") as temporary:
        output_root = Path(temporary) / "evidence"

        # When: the pinned local rhwp engine extracts and renders the document.
        result = _run(format_name, output_root)

        # Then: the compatible observation is grounded in pristine inputs and raw files.
        assert result.returncode == 0, result.stderr
        observation = json.loads((output_root / "visual-observation.json").read_text())
        assert json.loads(result.stdout) == observation
        assert observation["toolID"] == "edwardkim-rhwp-local-visual-observer"
        assert observation["fixtureID"] == "basic-client-interoperability"
        assert observation["fixtureHash"] == fixture_hash
        assert observation["format"] == format_name
        assert observation["artifactHash"] == artifact_hash
        assert observation["expectedPageCount"] == 1
        assert observation["observedPageCount"] == 1
        assert observation["missingAuthoredElementIDs"] == []
        assert observation["unexpectedBlankPageNumbers"] == []
        assert observation["textBoundsCoverage"] == 1
        assert "Apple SD Gothic Neo Regular" in observation["fonts"]
        assert observation["osVersion"]
        assert observation["osBuild"]

        manifest = json.loads((output_root / observation["evidencePath"]).read_text())
        assert observation["evidenceHash"] == _sha256(
            output_root / observation["evidencePath"]
        )
        assert manifest["tool"]["sha256"] == RHWP_SHA256
        assert manifest["inputs"]["artifact"] == {
            "path": str(artifact.relative_to(ROOT)),
            "pristineBeforeSha256": artifact_hash,
            "pristineAfterSha256": artifact_hash,
        }
        assert manifest["inputs"]["fixture"] == {
            "path": str(FIXTURE.relative_to(ROOT)),
            "pristineBeforeSha256": fixture_hash,
            "pristineAfterSha256": fixture_hash,
        }
        assert manifest["analysis"]["extractedElementIDs"] == EXPECTED_ELEMENT_IDS
        assert manifest["analysis"]["renderedElementIDs"] == EXPECTED_ELEMENT_IDS
        assert manifest["analysis"]["boundedElementIDs"] == EXPECTED_ELEMENT_IDS
        assert manifest["analysis"]["pageCountSources"] == {
            "info": 1,
            "text": 1,
            "svg": 1,
            "renderTree": 1,
        }
        evidence_paths = {entry["path"] for entry in manifest["evidence"]}
        assert "info.json" in evidence_paths
        assert "export-text.json" in evidence_paths
        assert "export-svg-manifest.json" in evidence_paths
        assert "render-tree/render_tree_001.json" in evidence_paths
        assert any(path.startswith("svg/") and path.endswith(".svg") for path in evidence_paths)
        for entry in manifest["evidence"]:
            evidence_path = output_root / entry["path"]
            assert evidence_path.is_file()
            assert entry["sha256"] == _sha256(evidence_path)
            assert entry["sizeBytes"] == evidence_path.stat().st_size
        assert _sha256(artifact) == artifact_hash
        assert _sha256(FIXTURE) == fixture_hash


def test_rhwp_visual_observation_refuses_an_existing_output() -> None:
    # Given: an occupied evidence directory whose prior content must survive.
    with tempfile.TemporaryDirectory(prefix="rhwp-visual-test-", dir=ROOT / "output") as temporary:
        output_root = Path(temporary) / "evidence"
        output_root.mkdir()
        sentinel = output_root / "preserve.txt"
        sentinel.write_text("preserve", encoding="utf-8")

        # When: another observation targets the same output root.
        result = _run("hwp", output_root)

        # Then: the tool rejects the target before running or changing evidence.
        assert result.returncode != 0
        assert "output root already exists" in result.stderr
        assert list(output_root.iterdir()) == [sentinel]
        assert sentinel.read_text(encoding="utf-8") == "preserve"
