from __future__ import annotations

import hashlib
import json
import subprocess
from functools import lru_cache
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FORMATS = ("hwpx", "hwp", "docx", "markdown")


@lru_cache(maxsize=1)
def _app_binary() -> Path:
    subprocess.run(
        ["swift", "build"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    binary = ROOT / ".build" / "debug" / "PublicDocumentApp"
    assert binary.is_file()
    return binary


def _run_compatibility(evidence_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(_app_binary()), "--compatibility-self-test", str(evidence_root)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _verify_compatibility(
    receipt: Path,
    observations: Path,
    *,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(_app_binary()), "--verify-compatibility-observations", str(receipt), str(observations)],
        cwd=ROOT,
        check=check,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_frozen_compatibility_corpus_covers_manifest_and_binds_fixture_hashes() -> None:
    # Given: the frozen authoring manifest and AC-07 compatibility corpus.
    capability_root = ROOT / "Resources" / "Capabilities"
    compatibility_root = ROOT / "Resources" / "Compatibility"
    authoring = json.loads(
        (capability_root / "authoring-capabilities-1.0.0.json").read_text()
    )
    corpus = json.loads(
        (compatibility_root / "compatibility-corpus-1.0.0.json").read_text()
    )

    # When: fixture coverage and immutable source identities are inspected.
    covered = set().union(*(set(fixture["capabilities"]) for fixture in corpus["fixtures"]))
    required = {element["id"] for element in authoring["elements"]}
    fixture_hashes = {
        fixture["id"]: "sha256:"
        + hashlib.sha256(
            (compatibility_root / fixture["projectPath"]).read_bytes()
        ).hexdigest()
        for fixture in corpus["fixtures"]
    }

    # Then: every frozen capability is covered and every project hash is exact.
    assert corpus["status"] == "frozen"
    assert corpus["manifestVersion"] == authoring["manifestVersion"] == "1.0.0"
    assert required <= covered
    assert fixture_hashes == {
        "basic-client-interoperability": (
            "sha256:d4f4d8d4fa44db5db7325960c75d628ce780aa50128bddbf31b59a524823e034"
        ),
        "authoring-universe": (
            "sha256:da4cac83207b2ca76f98cb49aff0a571996dc7495d2fa595de845444d5adfb3d"
        ),
    }
    assert fixture_hashes == {
        fixture["id"]: fixture["projectHash"] for fixture in corpus["fixtures"]
    }
    assert {fixture["id"]: tuple(fixture["formats"]) for fixture in corpus["fixtures"]} == {
        "basic-client-interoperability": FORMATS,
        "authoring-universe": FORMATS,
    }
    package_script = (ROOT / "scripts" / "package-macos-app.sh").read_text()
    assert 'Resources/Compatibility" "$destination/Contents/Resources/Compatibility' in package_script


def test_local_compatibility_run_keeps_four_verdict_classes_separate(
    tmp_path: Path,
) -> None:
    # Given: the frozen corpus and no externally supplied client observations.
    evidence_root = tmp_path / "compatibility"

    # When: the app evaluates locally reproducible evidence.
    result = _run_compatibility(evidence_root)
    receipt = json.loads(result.stdout)

    # Then: each verdict remains independent and no unavailable evidence becomes a pass.
    assert receipt["corpusVersion"] == "1.0.0"
    assert receipt["manifestVersion"] == "1.0.0"
    assert receipt["structuralVerdict"] == "pass"
    assert receipt["semanticVerdict"] == "pass"
    assert receipt["visualVerdict"] == "blocked"
    assert receipt["clientVerdict"] == "blocked"
    assert receipt["overallVerdict"] == "blocked"
    assert "table+rich-inline" in receipt["capabilityGaps"]["hwpx"]
    assert "formula" in receipt["capabilityGaps"]["hwp"]
    assert "unordered-list" in receipt["capabilityGaps"]["docx"]
    assert "formula" in receipt["capabilityGaps"]["markdown"]
    assert receipt["requiredClientOperations"] == {
        "docx": ["genoffice-docs-reopen", "microsoft-word-reopen"],
        "hwp": ["hancom-official-reopen", "polaris-office-reopen"],
        "hwpx": ["hancom-official-reopen", "polaris-office-reopen"],
        "markdown": ["approved-rendering", "commonmark-validate"],
    }
    dispositions = {
        (row["fixtureID"], row["format"]): (
            row["disposition"],
            row["capabilityGaps"],
        )
        for row in receipt["dispositions"]
    }
    governed_gaps = {
        "hwpx": ["approval-grid", "formula", "list-item", "table", "table+rich-inline", "unordered-list"],
        "hwp": ["approval-grid", "formula", "list-item", "table", "table+rich-inline", "unordered-list"],
        "docx": ["list-item", "unordered-list"],
        "markdown": ["formula", "list-item", "unordered-list"],
    }
    assert receipt["capabilityGaps"] == governed_gaps
    assert dispositions == {
        **{
            ("basic-client-interoperability", format_name): ("artifact-validated", [])
            for format_name in FORMATS
        },
        **{
            ("authoring-universe", format_name): ("semantic-loss-blocked", gaps)
            for format_name, gaps in governed_gaps.items()
        },
    }
    assert {(row["fixtureID"], row["format"]) for row in receipt["artifacts"]} == {
        ("basic-client-interoperability", format_name) for format_name in FORMATS
    }
    for artifact in receipt["artifacts"]:
        assert artifact["fixtureHash"].startswith("sha256:")
        assert artifact["artifactHash"].startswith("sha256:")
        assert (evidence_root / artifact["relativePath"]).is_file()


def test_client_observation_gate_requires_exact_environment_and_artifact_identity(
    tmp_path: Path,
) -> None:
    # Given: a generated compatibility receipt with no external observations.
    evidence_root = tmp_path / "compatibility"
    _run_compatibility(evidence_root)
    receipt_path = evidence_root / "compatibility-receipt.json"
    receipt = json.loads(receipt_path.read_text())
    artifact = receipt["artifacts"][0]
    observation = {
        "observationID": "observation-test-mismatched-artifact",
        "clientID": "polaris-office",
        "clientName": "Polaris Office",
        "clientVersion": "9.0.80",
        "clientBuild": "97427",
        "osVersion": "macOS 26.5.2",
        "osBuild": "25F84",
        "fonts": ["Apple SD Gothic Neo Regular"],
        "timestamp": "2026-08-09T12:00:00+09:00",
        "fixtureID": artifact["fixtureID"],
        "fixtureHash": artifact["fixtureHash"],
        "format": artifact["format"],
        "artifactHash": "sha256:" + "0" * 64,
        "operation": "polaris-office-reopen",
        "diagnostics": "test-only mismatched artifact",
        "verdict": "pass",
    }
    observation_path = tmp_path / "observation.json"
    observation_path.write_text(json.dumps([observation]), encoding="utf-8")

    # When: the observation is merged into the machine-readable receipt.
    result = _verify_compatibility(receipt_path, observation_path)

    # Then: an artifact identity mismatch is rejected instead of producing a pass.
    assert result.returncode != 0
    assert "artifactHash" in result.stderr
