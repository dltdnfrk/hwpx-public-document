from __future__ import annotations

from pathlib import Path

from tests.seed_criterion_fixture_support import evidence, write_json


FORMATS = ["hwpx", "hwp", "docx", "markdown"]


def write_ac01_fixture(root: Path) -> None:
    genoffice_commit = "d8305ff2dc152593a1ec5639d77e6860c6a512bd"
    rhwp_commit = "2dced7bfe10c6597cead634264c7c1781c01f1e7"
    rhwp_hash = "sha256:" + "9" * 64
    source_evidence = []
    for index in range(8):
        relative = f"runtime/ac01-source-{index}.json"
        write_json(root, relative, {"index": index})
        source_evidence.append(evidence(root, relative))
    port_path = "artifacts/provenance/genoffice-docs-port.json"
    write_json(
        root,
        port_path,
        {
            "integrationMode": "pinned-adapter-runtime-fork",
            "upstream": {"commit": genoffice_commit},
            "portBoundary": {
                "directPackageRuntimeLinkage": True,
                "upstreamRuntimeFilesBundled": True,
            },
        },
    )
    write_json(
        root,
        "artifacts/provenance/upstream-lock.json",
        {
            "upstreams": [
                {
                    "name": "genoffice",
                    "repository": "https://github.com/genspark-ai/genoffice.git",
                    "commit": genoffice_commit,
                    "license": "Apache-2.0",
                    "integration_mode": "pinned-adapter-runtime-fork",
                    "port_manifest_sha256": evidence(root, port_path)["sha256"],
                    "direct_package_runtime_linkage": True,
                    "upstream_runtime_files_bundled": True,
                },
                {
                    "name": "rhwp",
                    "commit": rhwp_commit,
                    "local_patchset": {"bundled_arm64_binary_sha256": rhwp_hash},
                },
            ],
            "runtime_scope": {
                "integration_mode": "pinned-adapter-runtime-fork",
                "direct_upstream_package_linkage": True,
                "bundled_upstream_runtime_files": True,
            },
        },
    )
    packages = [
        {"name": "GenOffice Docs", "versionInfo": genoffice_commit},
        {"name": "rhwp", "versionInfo": rhwp_commit},
    ] + [{"name": f"dependency-{index}", "versionInfo": "1"} for index in range(205)]
    write_json(
        root,
        "artifacts/provenance/sbom.spdx.json",
        {"packages": packages, "relationships": [{"index": index} for index in range(207)]},
    )
    notices = root / "artifacts/provenance/THIRD_PARTY_NOTICES.md"
    notices.parent.mkdir(parents=True, exist_ok=True)
    notices.write_text("GenOffice Apache-2.0\nrhwp MIT\n", encoding="utf-8")
    runtime_files = {
        "GenOfficeFork/browser.tsx": "export const editor = 'docs';",
        "GenOfficeFork/upstream-lock.json": '{"repository":"https://github.com/genspark-ai/genoffice.git"}',
        "scripts/build-genoffice-runtime.mjs": "export const build = 'pinned';",
        "Resources/GenOffice/public-document-genoffice.js": "customElements.define('public-document-genoffice', class {});",
        "Resources/GenOffice/genoffice-docx-normalize.cjs": "module.exports = { normalize: true };",
        "Resources/Engines/node": "arm64-node",
    }
    for relative, contents in runtime_files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(contents, encoding="utf-8")
    browser = evidence(root, "Resources/GenOffice/public-document-genoffice.js")
    docx = evidence(root, "Resources/GenOffice/genoffice-docx-normalize.cjs")
    node = evidence(root, "Resources/Engines/node")
    adapter = evidence(root, "GenOfficeFork/browser.tsx")
    upstream_lock = evidence(root, "GenOfficeFork/upstream-lock.json")
    build_script = evidence(root, "scripts/build-genoffice-runtime.mjs")
    inputs = sorted([
        {"path": "adapter/GenOfficeFork/browser.tsx", "sha256": adapter["sha256"][7:]},
        {"path": "adapter/GenOfficeFork/upstream-lock.json", "sha256": upstream_lock["sha256"][7:]},
        {"path": "adapter/scripts/build-genoffice-runtime.mjs", "sha256": build_script["sha256"][7:]},
        {"path": "dependencies/node_modules/react/index.js", "sha256": "1" * 64},
        {"path": "upstream/LICENSE", "sha256": "9" * 64},
        {"path": "upstream/apps/docs/src/renderer/App.tsx", "sha256": "2" * 64},
        {"path": "upstream/package-lock.json", "sha256": "a" * 64},
    ], key=lambda entry: entry["path"])
    packages = [
        {"name": "@genoffice/docx-engine", "version": "0.1.0", "license": "Apache-2.0", "packageJsonSha256": "3" * 64},
        {"name": "@genoffice/ui", "version": "0.1.0", "license": "Apache-2.0", "packageJsonSha256": "4" * 64},
        {"name": "@tiptap/core", "version": "3.0.0", "license": "MIT", "packageJsonSha256": "5" * 64},
        {"name": "react", "version": "19.0.0", "license": "MIT", "packageJsonSha256": "6" * 64},
        {"name": "react-dom", "version": "19.0.0", "license": "MIT", "packageJsonSha256": "7" * 64},
    ]
    build_tool = {
        "name": "esbuild",
        "version": "0.25.12",
        "license": "MIT",
        "packageJsonSha256": "8" * 64,
    }
    input_lock = {
        "schemaVersion": 1,
        "upstreamCommit": genoffice_commit,
        "buildTool": build_tool,
        "inputs": inputs,
        "packages": packages,
    }
    write_json(
        root,
        "GenOfficeFork/runtime-input-lock.json",
        input_lock,
    )
    write_json(root, "artifacts/provenance/genoffice-runtime-input-lock.json", input_lock)
    input_lock_evidence = evidence(root, "GenOfficeFork/runtime-input-lock.json")
    write_json(
        root,
        "artifacts/provenance/genoffice-runtime-manifest.json",
        {
            "schemaVersion": 1,
            "upstream": {"repository": "https://github.com/genspark-ai/genoffice.git", "commit": genoffice_commit, "license": "Apache-2.0"},
            "buildTool": build_tool,
            "inputs": inputs,
            "packages": packages,
            "inputLock": {
                "sourcePath": input_lock_evidence["path"],
                "packagedPath": "Provenance/genoffice-runtime-input-lock.json",
                "sha256": input_lock_evidence["sha256"][7:],
            },
            "outputs": [
                {"path": "GenOffice/public-document-genoffice.js", "sha256": browser["sha256"][7:], "sizeBytes": len(runtime_files[browser["path"]])},
                {"path": "GenOffice/genoffice-docx-normalize.cjs", "sha256": docx["sha256"][7:], "sizeBytes": len(runtime_files[docx["path"]])},
            ],
            "node": {"version": "22.17.1", "sourcePath": "Engines/node", "sha256": node["sha256"][7:], "sizeBytes": len(runtime_files[node["path"]]), "architecture": "arm64", "linkedLibraries": ["/usr/lib/libSystem.B.dylib"]},
            "runtime": {"browserBundlePath": "GenOffice/public-document-genoffice.js", "docxCliPath": "GenOffice/genoffice-docx-normalize.cjs", "customElementTag": "public-document-genoffice-editor", "readyEvent": "public-document-genoffice-ready", "changeEvent": "public-document-genoffice-change", "offline": True},
        },
    )
    write_json(
        root,
        "artifacts/provenance/foundation-runtime.json",
        {
            "architecture": "arm64",
            "codesignVerification": "pass",
            "rhwpBinaryHash": rhwp_hash,
            "sourceEvidence": source_evidence,
        },
    )
    studio = root / "Resources/Studio"
    studio.mkdir(parents=True, exist_ok=True)
    for name in ["index.html", "styles.css", "app.js"]:
        (studio / name).write_text("owned document studio", encoding="utf-8")


def write_ac05_fixture(root: Path, *, flattening_consent: bool = False) -> None:
    write_json(root, "runtime/ac05-source-a.json", {"source": "a"})
    write_json(root, "runtime/ac05-source-b.json", {"source": "b"})
    write_json(
        root,
        "artifacts/formats/authoring-capability-manifest.json",
        {"elements": [{"id": "paragraph"}]},
    )
    write_json(
        root,
        "artifacts/formats/format-capability-matrix.json",
        {
            "classifications": ["lossless", "visual-only-flattening", "semantic-loss"],
            "matrix": [{"capability": "paragraph", **{name: "lossless" for name in FORMATS}}],
        },
    )
    losses = [
        {
            "classification": "semantic-loss",
            "elementID": "element-1",
            "elementPath": "elements/0",
            "fallback": "blocked rather than flattened",
            "format": "hwpx",
            "requiresConsent": False,
        }
    ]
    write_json(root, "artifacts/formats/loss-reports.jsonl", losses)
    results = [
        {
            "format": name,
            "structuralValid": True,
            "semanticValid": True,
            "validation": {
                "structuralValid": True,
                "semanticValid": True,
                "orderedElements": [{"elementID": "element-1"}],
            },
        }
        for name in FORMATS
    ]
    receipt = {
        "selectedFormats": FORMATS,
        "publishedFormats": FORMATS,
        "blockedFormats": [],
        "failedFormats": [],
        "failures": [],
        "allAuthoredElementIDsPreserved": True,
        "flatteningConsentRecorded": flattening_consent,
        "lossReports": losses,
        "results": results,
    }
    write_json(
        root,
        "artifacts/formats/export-validation-evidence.json",
        {
            "receipts": [receipt],
            "sourceEvidence": [
                evidence(root, "runtime/ac05-source-a.json"),
                evidence(root, "runtime/ac05-source-b.json"),
            ],
        },
    )
