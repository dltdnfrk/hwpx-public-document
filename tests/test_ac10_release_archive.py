from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

from tests import ac10_archive_fixture


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_SCRIPT = ROOT / "scripts/package-release-archive.sh"
FORBIDDEN_GENOFFICE_RUNTIME = re.compile(
    r"genspark|AiPanel|electron-updater|apps/(sheets|slides|pdf|shell|markdown)"
    r"|packages/(ai-provider|ai-search|agent-core|pptx-engine|pptx-render|electron-utils)"
    r"|fetch\s*\(|WebSocket|XMLHttpRequest|sendBeacon|new\s+Function|eval\s*\(",
    re.IGNORECASE,
)


def test_release_archive_reopens_as_clean_verified_app(tmp_path: Path) -> None:
    # Given: a real packaged app whose published copy acquired Finder metadata.
    package_parent = tmp_path / "package"
    package_parent.mkdir()
    app = package_parent / "PublicDocument.app"
    package_environment = os.environ.copy()
    package_environment["PUBLIC_DOCUMENT_PACKAGE_PARENT"] = str(package_parent)
    subprocess.run(
        [str(ROOT / "scripts/package-macos-app.sh"), str(app)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=300,
        env=package_environment,
    )
    ac10_archive_fixture.write_archive_evidence(package_parent)
    finder_info = "00" * 19 + "01" + "00" * 12
    subprocess.run(
        ["xattr", "-wx", "com.apple.FinderInfo", finder_info, str(app)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert subprocess.run(
        ["codesign", "--verify", "--deep", "--strict", str(app)],
        capture_output=True,
        text=True,
    ).returncode != 0
    archive = tmp_path / "PublicDocumentStudio-0.1.0.zip"

    # When: the canonical resource-fork-free release archive is produced.
    subprocess.run(
        [str(ARCHIVE_SCRIPT), str(app), str(archive)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    repeated_archive = tmp_path / "PublicDocumentStudio-0.1.0-repeat.zip"
    subprocess.run(
        [str(ARCHIVE_SCRIPT), str(app), str(repeated_archive)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert hashlib.sha256(repeated_archive.read_bytes()).hexdigest() == hashlib.sha256(
        archive.read_bytes()
    ).hexdigest()

    # Then: independent extraction contains the app and its complete evidence bundle.
    extraction = tmp_path / "independent-extraction"
    extraction.mkdir()
    subprocess.run(
        ["ditto", "-x", "-k", str(archive), str(extraction)],
        check=True,
        capture_output=True,
        text=True,
    )
    extracted_app = extraction / "PublicDocument.app"
    extracted_evidence = extraction / "Evidence"
    ac10_archive_fixture.assert_manifest_links_and_verdicts(extraction)

    # Then: the companion receipt and inventory bind the fresh extraction.
    receipt_path = archive.with_suffix(".verification.json")
    inventory_path = archive.with_suffix(".SHA256SUMS")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["schemaVersion"] == 2
    assert receipt["archive"] == {
        "file": archive.name,
        "format": "zip",
        "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "sizeBytes": archive.stat().st_size,
    }
    assert receipt["app"]["architecture"] == "arm64"
    assert receipt["app"]["bundleIdentifier"] == "com.muni.public-document"
    assert receipt["app"]["codesignVerification"] == "pass"
    assert receipt["verification"] == {
        "archiveExtendedAttributes": "excluded",
        "extractedInventoryComparison": "pass",
        "freshTemporaryExtraction": True,
        "sha256InventoryRecheck": "pass",
    }
    resource_paths = {row["path"] for row in receipt["app"]["resourceTrees"]}
    assert resource_paths == {
        "Contents/Resources/Capabilities",
        "Contents/Resources/Compatibility",
        "Contents/Resources/Engines",
        "Contents/Resources/GenOffice",
        "Contents/Resources/Legal",
        "Contents/Resources/Performance",
        "Contents/Resources/Provenance",
        "Contents/Resources/Studio",
        "Contents/Resources/Templates",
    }
    assert receipt["bundle"]["sha256Inventory"]["file"] == inventory_path.name
    assert receipt["bundle"]["sha256Inventory"]["sha256"] == hashlib.sha256(
        inventory_path.read_bytes()
    ).hexdigest()
    assert receipt["evidence"]["root"] == "Evidence"
    assert receipt["evidence"]["manifestResolution"] == "pass"
    assert receipt["evidence"]["internalInventoryRecheck"] == "pass"
    subprocess.run(
        ["codesign", "--verify", "--deep", "--strict", str(extracted_app)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert subprocess.run(
        ["xattr", "-p", "com.apple.FinderInfo", str(extracted_app)],
        capture_output=True,
        text=True,
    ).returncode != 0
    ac10_archive_fixture.assert_inventory_matches(extraction, inventory_path)
    inventory_rows = inventory_path.read_text(encoding="utf-8").splitlines(
        keepends=True
    )
    for resource_tree in receipt["app"]["resourceTrees"]:
        prefix = f"  PublicDocument.app/{resource_tree['path']}/"
        matching_rows = [row for row in inventory_rows if prefix in row]
        assert len(matching_rows) == resource_tree["fileCount"]
        assert hashlib.sha256("".join(matching_rows).encode()).hexdigest() == (
            resource_tree["treeSha256"]
        )
    for collection in ("provenanceArtifacts", "engineArtifacts"):
        for artifact_receipt in receipt["app"][collection]:
            artifact = extracted_app / artifact_receipt["path"]
            assert hashlib.sha256(artifact.read_bytes()).hexdigest() == (
                artifact_receipt["sha256"]
            )
    assert {
        row["path"] for row in receipt["app"]["provenanceArtifacts"]
    } >= {
        "Contents/Resources/Provenance/rhwp-dependency-lock.json",
        "Contents/Resources/Provenance/genoffice-node-runtime-lock.json",
        "Contents/Resources/Provenance/genoffice-runtime-input-lock.json",
        "Contents/Resources/Provenance/sbom.spdx.json",
        "Contents/Resources/Provenance/upstream-lock.json",
    }
    engine_receipts = {
        row["path"]: row["sha256"] for row in receipt["app"]["engineArtifacts"]
    }
    assert set(engine_receipts) == {
        "Contents/Resources/Engines/node",
        "Contents/Resources/Engines/rhwp",
    }
    for engine_path, engine_hash in engine_receipts.items():
        assert hashlib.sha256((extracted_app / engine_path).read_bytes()).hexdigest() == (
            engine_hash
        )

    resources = extracted_app / "Contents/Resources"
    genoffice_manifest = json.loads(
        (resources / "GenOffice/runtime-manifest.json").read_text(encoding="utf-8")
    )
    upstream_lock = json.loads(
        (resources / "Provenance/upstream-lock.json").read_text(encoding="utf-8")
    )
    genoffice_upstream = next(
        row for row in upstream_lock["upstreams"] if row["name"] == "genoffice"
    )
    assert genoffice_manifest["upstream"] == {
        "repository": genoffice_upstream["repository"],
        "commit": genoffice_upstream["commit"],
        "license": "Apache-2.0",
    }
    input_lock = resources / "Provenance/genoffice-runtime-input-lock.json"
    node_lock = resources / "Provenance/genoffice-node-runtime-lock.json"
    assert hashlib.sha256(input_lock.read_bytes()).hexdigest() == (
        genoffice_manifest["inputLock"]["sha256"]
    )
    assert hashlib.sha256(node_lock.read_bytes()).hexdigest() == (
        genoffice_manifest["node"]["lock"]["sha256"]
    )
    node = resources / "Engines/node"
    assert hashlib.sha256(node.read_bytes()).hexdigest() == genoffice_manifest["node"][
        "sha256"
    ]
    assert node.stat().st_size == genoffice_manifest["node"]["sizeBytes"]
    assert subprocess.run(
        ["lipo", "-archs", str(node)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip() == "arm64"
    linked_libraries = subprocess.run(
        ["otool", "-L", "-arch", "arm64", str(node)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()[1:]
    assert linked_libraries
    assert all(
        library.strip().startswith(("/System/Library/", "/usr/lib/"))
        for library in linked_libraries
    )
    for output in genoffice_manifest["outputs"]:
        artifact = resources / output["path"]
        assert artifact.stat().st_size == output["sizeBytes"]
        assert hashlib.sha256(artifact.read_bytes()).hexdigest() == output["sha256"]
    for runtime_name in (
        "public-document-genoffice.js",
        "genoffice-docx-normalize.cjs",
    ):
        runtime_text = (resources / "GenOffice" / runtime_name).read_text(
            encoding="utf-8"
        )
        assert FORBIDDEN_GENOFFICE_RUNTIME.search(runtime_text) is None
    assert subprocess.run(
        ["xattr", "-p", "com.apple.FinderInfo", str(app)],
        capture_output=True,
        text=True,
    ).returncode == 0


def test_release_archive_refuses_existing_outputs(tmp_path: Path) -> None:
    # Given: an existing canonical archive that must be preserved.
    app = tmp_path / "PublicDocument.app"
    app.mkdir()
    archive = tmp_path / "PublicDocumentStudio-0.1.0.zip"
    archive.write_bytes(b"preserve")

    # When: publication is requested at the occupied path.
    result = subprocess.run(
        [str(ARCHIVE_SCRIPT), str(app), str(archive)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )

    # Then: the script fails before touching the existing release.
    assert result.returncode != 0
    assert archive.read_bytes() == b"preserve"
