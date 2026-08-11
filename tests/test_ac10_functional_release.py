from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
BUILD_SCRIPT = ROOT / "scripts/build-ac10-functional-release.sh"


def _write_source_map(path: Path, unsafe_path: str | None = None) -> Path:
    evidence_document = "docs/ac-10-functional-release-evidence.md"
    criteria = {
        f"AC-{criterion:02}": {"source": evidence_document}
        for criterion in range(1, 11)
    }
    criteria["AC-05"] = {"source": "provenance/rhwp-dependency-lock.json"}
    criteria["AC-07"] = {"source": "provenance/genoffice-docs-port.json"}
    criteria["AC-08"] = {"source": "scripts/package-release-archive.sh"}
    criteria["AC-09"] = {
        "source": "Resources/Release/release-manifest-1.0.0.json"
    }
    criteria["AC-10"] = {
        "archive": "../not-built-yet.zip",
        "archiveVerification": "/not-built-yet.verification.json",
        "releaseManifest": "not-built-yet/release-manifest.json",
        "sha256Inventory": "not-built-yet/SHA256SUMS",
    }
    if unsafe_path is not None:
        criteria["AC-07"] = {"source": unsafe_path}
    path.write_text(
        json.dumps({"schemaVersion": 1, "criteria": criteria}),
        encoding="utf-8",
    )
    return path


def test_ac10_builder_contains_no_ephemeral_evidence_roots() -> None:
    # Given: the functional-release assembly implementation.
    script = BUILD_SCRIPT.read_text(encoding="utf-8")

    # When: its evidence source contract is inspected.
    forbidden_roots = (
        "final-seed.",
        "runtime-seed.",
        "output/playwright/ac08",
        "voiceover-full.",
        "microsoft-word-final.",
        "markdown-final.",
    )

    # Then: only the canonical source-map seam remains.
    assert all(root not in script for root in forbidden_roots)
    assert "provenance/seed-evidence-sources.json" in script
    assert "jq" in script
    assert '.criteria["AC-10"]' not in script
    assert "archiveVerification" not in script
    assert '.overallVerdict == "pass"' in script
    assert 'all(.passed == true)' in script


def test_ac10_builder_rejects_traversal_source_entry(tmp_path: Path) -> None:
    # Given: a source map whose evidence path escapes the project root.
    source_map = _write_source_map(
        tmp_path / "traversal-source-map.json",
        "../outside-seed-evidence.json",
    )
    destination = tmp_path / "traversal-release"

    # When: functional-release assembly validates the source map.
    result = subprocess.run(
        [str(BUILD_SCRIPT), str(destination), str(source_map)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )

    # Then: validation fails before publishing or building an app.
    assert result.returncode != 0
    assert not destination.exists()


def test_ac10_builder_rejects_absolute_source_entry(tmp_path: Path) -> None:
    # Given: a source map containing an absolute evidence path.
    source_map = _write_source_map(
        tmp_path / "absolute-source-map.json",
        "/etc/hosts",
    )
    destination = tmp_path / "absolute-release"

    # When: functional-release assembly validates the source map.
    result = subprocess.run(
        [str(BUILD_SCRIPT), str(destination), str(source_map)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )

    # Then: validation fails closed without publishing a release.
    assert result.returncode != 0
    assert not destination.exists()


def test_ac10_builder_rejects_normalized_traversal_entry(tmp_path: Path) -> None:
    # Given: an in-root path that still contains a traversal segment.
    source_map = _write_source_map(
        tmp_path / "normalized-traversal-source-map.json",
        "docs/../docs/ac-10-functional-release-evidence.md",
    )
    destination = tmp_path / "normalized-traversal-release"

    # When: functional-release assembly validates the source-map grammar.
    result = subprocess.run(
        [str(BUILD_SCRIPT), str(destination), str(source_map)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )

    # Then: even resolvable traversal is rejected before publication.
    assert result.returncode != 0
    assert not destination.exists()


def test_ac10_bundle_is_offline_unsigned_and_truthfully_bound(tmp_path: Path) -> None:
    # Given: an empty destination on the recorded Apple Silicon Mac.
    destination = tmp_path / "PublicDocumentStudio-Functional-0.1.0"
    source_map = _write_source_map(tmp_path / "seed-evidence-sources.json")

    # When: the AC-10 functional release is assembled without credentials or network.
    subprocess.run(
        [str(BUILD_SCRIPT), str(destination), str(source_map)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=300,
        env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin"},
    )

    # Then: the local app and evidence bundle bind the exact functional-release scope.
    app = destination / "PublicDocument.app"
    evidence = destination / "Evidence"
    manifest = json.loads((evidence / "release-manifest.json").read_text())
    assert (app / "Contents/MacOS/PublicDocumentApp").is_file()
    assert manifest["releaseType"] == "unsigned-local-functional"
    assert manifest["architecture"] == "arm64"
    assert manifest["offlineContract"] == {
        "accountRequired": False,
        "networkRequired": False,
        "providerCredentialRequired": False,
    }
    assert manifest["formats"] == ["hwpx", "hwp", "docx", "markdown"]
    assert manifest["excludedRequirements"] == [
        "legacy-doc",
        "arbitrary-external-document-round-trip",
        "alternative-hwp-converter",
        "other-office-products",
        "developer-id-signing",
        "notarization",
        "updater",
        "dmg",
        "gatekeeper-distribution",
    ]
    assert manifest["upstreamPins"] == {
        "genoffice": "d8305ff2dc152593a1ec5639d77e6860c6a512bd",
        "rhwp": "2dced7bfe10c6597cead634264c7c1781c01f1e7",
    }
    criteria = {row["criterion"]: row["verdict"] for row in manifest["criteria"]}
    assert criteria == {
        "AC-01": "pass",
        "AC-02": "pass",
        "AC-03": "pass",
        "AC-04": "pass",
        "AC-05": "pass",
        "AC-06": "pass",
        "AC-07": "blocked",
        "AC-08": "pass",
        "AC-09": "pass",
        "AC-10": "blocked",
    }
    assert manifest["functionalSeedVerdict"] == "external-verification-blocked"
    assert manifest["distributionVerdict"] == "deferred"

    runtime = evidence / "Runtime/ac-10-packaged-app"
    assert json.loads((runtime / "ac-02/window-lifecycle.json").read_text()) == {
        "visibleWindowCount": 1
    }
    assert json.loads((runtime / "ac-04/ai-governance.json").read_text())[
        "offlineEditingAndExportAvailable"
    ] is True
    assert json.loads((runtime / "ac-05/export-hwp-family.json").read_text())[
        "publishedFormats"
    ] == ["hwpx", "hwp"]
    assert json.loads((runtime / "ac-05/export-loss-aware.json").read_text())[
        "publishedFormats"
    ] == ["docx", "markdown"]
    assert json.loads((runtime / "ac-06/batch-partial-failure.json").read_text())[
        "state"
    ] == "completed-with-errors"
    performance = json.loads((runtime / "ac-09/performance.json").read_text())
    assert performance["overallVerdict"] == "pass"
    assert len(performance["exportObservations"]) == 8
    foundation = json.loads((runtime / "ac-01/foundation-runtime.json").read_text())
    assert foundation["architecture"] == "arm64"
    assert foundation["codesignVerification"] == "pass"
    assert "sourceMapSHA256" not in foundation

    packaged_resources = app / "Contents/Resources"
    genoffice_manifest = json.loads(
        (packaged_resources / "GenOffice/runtime-manifest.json").read_text(
            encoding="utf-8"
        )
    )
    node = packaged_resources / "Engines/node"
    input_lock = packaged_resources / "Provenance/genoffice-runtime-input-lock.json"
    node_lock = packaged_resources / "Provenance/genoffice-node-runtime-lock.json"
    assert hashlib.sha256(node.read_bytes()).hexdigest() == genoffice_manifest["node"][
        "sha256"
    ]
    assert node.stat().st_size == genoffice_manifest["node"]["sizeBytes"]
    assert hashlib.sha256(input_lock.read_bytes()).hexdigest() == (
        genoffice_manifest["inputLock"]["sha256"]
    )
    assert hashlib.sha256(node_lock.read_bytes()).hexdigest() == (
        genoffice_manifest["node"]["lock"]["sha256"]
    )
    for output in genoffice_manifest["outputs"]:
        packaged_output = packaged_resources / output["path"]
        assert packaged_output.stat().st_size == output["sizeBytes"]
        assert hashlib.sha256(packaged_output.read_bytes()).hexdigest() == output[
            "sha256"
        ]

    declared_sources = {
        "Resources/Release/release-manifest-1.0.0.json",
        "docs/ac-10-functional-release-evidence.md",
        "provenance/genoffice-docs-port.json",
        "provenance/rhwp-dependency-lock.json",
        "scripts/package-release-archive.sh",
    }
    copied_sources = {
        str(path.relative_to(evidence / "CanonicalSources"))
        for path in (evidence / "CanonicalSources").rglob("*")
        if path.is_file()
    }
    assert copied_sources == declared_sources
    assert not (evidence / "Provenance/seed-evidence-sources.json").exists()
    publication = json.loads(
        (runtime / "final-publication-verification.json").read_text()
    )
    assert "sourceMapHash" not in publication
    assert publication["sourceMapBoundary"] == (
        "AC-10 source-map leaves are recorded outside the archive after publication."
    )

    checksum_rows = (evidence / "SHA256SUMS").read_text().splitlines()
    assert checksum_rows
    for row in checksum_rows:
        expected, relative_path = row.split("  ", 1)
        artifact = destination / relative_path
        assert artifact.is_file()
        assert hashlib.sha256(artifact.read_bytes()).hexdigest() == expected


def test_ac10_bundle_refuses_to_replace_an_existing_release(tmp_path: Path) -> None:
    # Given: a previously published functional bundle.
    destination = tmp_path / "existing-release"
    destination.mkdir()
    marker = destination / "preserve.txt"
    marker.write_text("keep", encoding="utf-8")

    # When: packaging is accidentally requested for the same destination.
    result = subprocess.run(
        [str(BUILD_SCRIPT), str(destination)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )

    # Then: publication fails without changing the existing release.
    assert result.returncode != 0
    assert marker.read_text(encoding="utf-8") == "keep"
