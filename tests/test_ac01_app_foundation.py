from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import TypedDict


ROOT = Path(__file__).resolve().parents[1]
GENOFFICE_COMMIT = "d8305ff2dc152593a1ec5639d77e6860c6a512bd"
RHWP_COMMIT = "2dced7bfe10c6597cead634264c7c1781c01f1e7"
RHWP_ENGINE_SHA256 = "a9fc072e61aa1cbf56fbd00943c4e4a33dd49aa7f6122f7b36e16ff476f7677b"
FORBIDDEN_RUNTIME_SURFACES = {"ee", "sheets", "slides", "pdf", "genspark"}


class OptionalUpstreamEntryFields(TypedDict, total=False):
    integration_mode: str
    port_manifest: str
    port_manifest_sha256: str
    direct_package_runtime_linkage: bool
    upstream_runtime_files_bundled: bool


class UpstreamEntry(OptionalUpstreamEntryFields):
    name: str
    commit: str


class RuntimeScope(TypedDict):
    integration_mode: str
    reviewed_upstream_source_scopes: list[str]
    shipped_local_port: list[str]
    direct_upstream_package_linkage: bool
    bundled_upstream_runtime_files: bool
    excluded: list[str]


class Review(TypedDict):
    status: str


class UpstreamLock(TypedDict):
    upstreams: list[UpstreamEntry]
    runtime_scope: RuntimeScope
    review: Review


class SpdxPackage(TypedDict):
    name: str
    versionInfo: str
    licenseConcluded: str


class SpdxDocument(TypedDict):
    packages: list[SpdxPackage]


class GenOfficeSourceFile(TypedDict):
    path: str
    sha256: str


class GenOfficeLocalArtifact(TypedDict):
    path: str
    sha256: str
    runtimeSurface: bool
    upstreamSources: list[str]
    portedResponsibilities: list[str]


class GenOfficePortBoundary(TypedDict):
    reviewedUpstreamSourceScopes: list[str]
    shippedLocalArtifacts: list[str]
    excludedUpstreamScopes: list[str]
    directPackageRuntimeLinkage: bool
    upstreamRuntimeFilesBundled: bool


class GenOfficePortUpstream(TypedDict):
    repository: str
    commit: str
    license: str
    sourceFiles: list[GenOfficeSourceFile]


class GenOfficePortManifest(TypedDict):
    schemaVersion: int
    integrationMode: str
    upstream: GenOfficePortUpstream
    portBoundary: GenOfficePortBoundary
    localArtifacts: list[GenOfficeLocalArtifact]


def _read_lock() -> UpstreamLock:
    with (ROOT / "provenance/upstream-lock.json").open(encoding="utf-8") as source:
        return json.load(source)


def _read_sbom() -> SpdxDocument:
    with (ROOT / "provenance/sbom.spdx.json").open(encoding="utf-8") as source:
        return json.load(source)


def _read_genoffice_port_manifest() -> GenOfficePortManifest:
    with (ROOT / "provenance/genoffice-docs-port.json").open(encoding="utf-8") as source:
        return json.load(source)


def test_upstream_lock_records_exact_reviewed_pins_and_docs_only_scope() -> None:
    # Given: the machine-readable source lock for the application release.
    lock = _read_lock()
    upstreams = lock["upstreams"]

    # When: the locked commits and included runtime surfaces are inspected.
    commits = {entry["name"]: entry["commit"] for entry in upstreams}
    genoffice = next(entry for entry in upstreams if entry["name"] == "genoffice")
    runtime_scope = lock["runtime_scope"]
    reviewed_scopes = set(runtime_scope["reviewed_upstream_source_scopes"])
    shipped_local_port = set(runtime_scope["shipped_local_port"])
    excluded = set(lock["runtime_scope"]["excluded"])

    # Then: both approved pins and the direct pinned adapter runtime are exact.
    assert commits == {"genoffice": GENOFFICE_COMMIT, "rhwp": RHWP_COMMIT}
    assert genoffice.get("integration_mode") == "pinned-adapter-runtime-fork"
    assert genoffice.get("port_manifest") == "provenance/genoffice-docs-port.json"
    manifest_digest = hashlib.sha256(
        (ROOT / "provenance/genoffice-docs-port.json").read_bytes()
    ).hexdigest()
    assert genoffice.get("port_manifest_sha256") == f"sha256:{manifest_digest}"
    assert genoffice.get("direct_package_runtime_linkage") is True
    assert genoffice.get("upstream_runtime_files_bundled") is True
    assert runtime_scope["integration_mode"] == "pinned-adapter-runtime-fork"
    assert reviewed_scopes == {
        "apps/docs/src/renderer",
        "packages/ui/src",
        "packages/docx-engine/src",
    }
    assert shipped_local_port == {
        "Resources/Studio/index.html",
        "Resources/Studio/styles.css",
        "Resources/Studio/app.js",
        "Sources/PublicDocumentApp/ExportSerializers.swift",
        "Sources/PublicDocumentApp/OfficialLayoutEngine.swift",
        "Resources/Studio/official-layout-profile.js",
        "Resources/Studio/easy-tools.js",
        "Sources/PublicDocumentApp/ExportValidation.swift",
    }
    assert runtime_scope["direct_upstream_package_linkage"] is True
    assert runtime_scope["bundled_upstream_runtime_files"] is True
    assert FORBIDDEN_RUNTIME_SURFACES <= excluded
    assert lock["review"]["status"] == "approved"


def test_genoffice_pinned_adapter_runtime_fork_binds_upstream_and_local_sources() -> None:
    # Given: the manifest for the pinned GenOffice adapter runtime fork.
    manifest = _read_genoffice_port_manifest()

    # When: the reviewed upstream inputs and shipped local outputs are indexed.
    upstream_hashes = {
        source["path"]: source["sha256"] for source in manifest["upstream"]["sourceFiles"]
    }
    local_artifacts = {
        artifact["path"]: artifact for artifact in manifest["localArtifacts"]
    }
    upstream_paths = set(upstream_hashes)
    boundary = manifest["portBoundary"]

    # Then: source inputs and local files are hash-bound to direct runtime linkage.
    assert manifest["schemaVersion"] == 1
    assert manifest["integrationMode"] == "pinned-adapter-runtime-fork"
    assert manifest["upstream"]["repository"] == "https://github.com/genspark-ai/genoffice.git"
    assert manifest["upstream"]["commit"] == GENOFFICE_COMMIT
    assert manifest["upstream"]["license"] == "Apache-2.0"
    assert upstream_hashes == {
        "apps/docs/src/renderer/App.tsx": "sha256:0cd748ce1b259c52a051f9976f785119e03f9dd6358b0f3136d3c75bf136b155",
        "apps/docs/src/renderer/components/Ribbon.tsx": "sha256:9b17e022ddd5f8d0d5ba728b1522a1f70b80b2734f0e1f5dc2cd55774da8019d",
        "apps/docs/src/renderer/components/NavPane.tsx": "sha256:2feb9209f9a92e7f54a71930d11502e4e3fbae3bc32a218b1903b0af6f4a03c7",
        "apps/docs/src/renderer/components/ribbon-tabs.tsx": "sha256:66a02109b0450ba5306f2f1a695810d55f47960cec0e22746489af11b9157f34",
        "apps/docs/src/renderer/file-actions.ts": "sha256:6699e5b841d5a2430018e9644110777c84b9f9525e88055e77661a65c4bfa08c",
        "apps/docs/src/renderer/styles.css": "sha256:1ea360efb6976e3a2a1378f51dd08723b2a8bade1ab5b34d6f0eccf69c89bae7",
        "packages/ui/src/index.ts": "sha256:761c3bddd885c8f5fd9d54bab6faa6009f30c95f31d36662fc51e37802fe5bcf",
        "packages/docx-engine/src/index.ts": "sha256:707d99e0ca80ba0ed2ed0752dfe90b9e5597d82023fb48eb4c3161d2350106ab",
        "packages/docx-engine/src/generate.ts": "sha256:067b6ba8f9e01c752fe572fa2be21770a37adf0cb88f23276505fae07597a79b",
        "packages/docx-engine/src/patch.ts": "sha256:ec2140201a91eaf9f46ddfa2bb99e3d39728ed390a5fd72412ed1a3639065b10",
    }
    assert set(local_artifacts) == set(boundary["shippedLocalArtifacts"])
    assert boundary["directPackageRuntimeLinkage"] is True
    assert boundary["upstreamRuntimeFilesBundled"] is True
    assert all(artifact["runtimeSurface"] for artifact in local_artifacts.values())
    assert all(artifact["portedResponsibilities"] for artifact in local_artifacts.values())
    assert all(set(artifact["upstreamSources"]) <= upstream_paths for artifact in local_artifacts.values())
    for relative_path, artifact in local_artifacts.items():
        expected_hash = hashlib.sha256((ROOT / relative_path).read_bytes()).hexdigest()
        assert artifact["sha256"] == f"sha256:{expected_hash}"


def test_sbom_binds_upstreams_to_commits_and_declared_licenses() -> None:
    # Given: the release SPDX document generated for the local application.
    sbom = _read_sbom()

    # When: upstream packages are indexed by their SPDX package names.
    packages = {package["name"]: package for package in sbom["packages"]}

    # Then: the exact source revisions and concluded licenses are reproducible.
    assert packages["GenOffice Docs"]["versionInfo"] == GENOFFICE_COMMIT
    assert packages["GenOffice Docs"]["licenseConcluded"] == "Apache-2.0"
    assert packages["rhwp"]["versionInfo"] == RHWP_COMMIT
    assert packages["rhwp"]["licenseConcluded"] == "MIT"


def test_runtime_accepts_only_the_bundled_pinned_rhwp_engine() -> None:
    source = (ROOT / "Sources" / "PublicDocumentApp" / "RhwpExport.swift").read_text(
        encoding="utf-8"
    )
    engine = ROOT / "Resources" / "Engines" / "rhwp"

    assert "PUBLIC_DOCUMENT_STUDIO_RHWP" not in source
    assert RHWP_ENGINE_SHA256 in source
    assert hashlib.sha256(engine.read_bytes()).hexdigest() == RHWP_ENGINE_SHA256


def test_sbom_includes_the_exact_pinned_rhwp_cargo_dependency_inventory() -> None:
    sbom = _read_sbom()
    lock = json.loads(
        (ROOT / "provenance" / "rhwp-dependency-lock.json").read_text(encoding="utf-8")
    )
    cargo_packages = [
        package
        for package in sbom["packages"]
        if package.get("SPDXID", "").startswith("SPDXRef-Cargo-")
    ]

    assert lock["cargoLockSHA256"] == (
        "sha256:64ff4041c1874c01c7a901b28df2639082836ced44df392cd37b3227d4772279"
    )
    assert lock["packageCount"] == len(cargo_packages) == 204
    assert all(package["versionInfo"] for package in cargo_packages)


def test_app_bundle_resources_use_owned_branding_and_no_forbidden_surface() -> None:
    # Given: every source and bundled resource that can reach the shipped app.
    runtime_files = [
        ROOT / "Sources/PublicDocumentApp/main.swift",
        ROOT / "Resources/Studio/index.html",
        ROOT / "Resources/Studio/styles.css",
        ROOT / "Resources/Studio/app.js",
    ]

    # When: runtime text is normalized for a forbidden-surface scan.
    runtime_text = "\n".join(path.read_text(encoding="utf-8") for path in runtime_files).lower()
    runtime_words = set(re.findall(r"[a-z]+", runtime_text))

    # Then: owned names are visible and rejected products and marks are unreachable.
    assert "문서작성기" in runtime_text
    assert FORBIDDEN_RUNTIME_SURFACES.isdisjoint(runtime_words)


def test_notices_ship_complete_license_evidence_for_both_upstreams() -> None:
    # Given: notice and license files copied into the application resources.
    notice = (ROOT / "Resources/Legal/THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    apache = (ROOT / "Resources/Legal/GenOffice-LICENSE.txt").read_text(encoding="utf-8")
    mit = (ROOT / "Resources/Legal/rhwp-LICENSE.txt").read_text(encoding="utf-8")

    # When/Then: each upstream, license grant, and immutable commit is inspectable offline.
    assert "Mainfunc, Inc." in notice
    assert GENOFFICE_COMMIT in notice
    assert RHWP_COMMIT in notice
    assert "Apache License\n                           Version 2.0" in apache
    assert "Copyright (c) 2025-2026 Edward Kim" in mit
    assert "Permission is hereby granted" in mit
