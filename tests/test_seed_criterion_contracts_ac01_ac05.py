from __future__ import annotations

import json
from pathlib import Path

from tests.seed_criterion_contract_support import run_contract
from tests.seed_criterion_fixture_ac01_ac05 import write_ac01_fixture, write_ac05_fixture
from tests.seed_criterion_fixture_support import evidence, write_json


def test_ac01_reads_genoffice_commit_from_manifest_upstream(tmp_path: Path) -> None:
    # Given: the approved port manifest records its commit in the real nested upstream shape.
    write_ac01_fixture(tmp_path)

    # When: AC-01 is independently evaluated.
    evaluation = run_contract({"action": "evaluate", "criterion": "AC-01", "root": str(tmp_path)})

    # Then: the manifest commit binds to the approved upstream lock.
    assert evaluation["verdict"] == "pass"


def test_ac01_rejects_manual_port_without_runtime_linkage(tmp_path: Path) -> None:
    # Given: the manifest has a pinned runtime but the port still declares no direct linkage.
    write_ac01_fixture(tmp_path)
    port_path = tmp_path / "artifacts/provenance/genoffice-docs-port.json"
    port = json.loads(port_path.read_text())
    port["portBoundary"]["directPackageRuntimeLinkage"] = False
    port["portBoundary"]["upstreamRuntimeFilesBundled"] = False
    write_json(tmp_path, "artifacts/provenance/genoffice-docs-port.json", port)

    # When: AC-01 evaluates the manual-only port claim.
    evaluation = run_contract({"action": "evaluate", "criterion": "AC-01", "root": str(tmp_path)})

    # Then: a source review without shipped runtime linkage cannot pass.
    assert evaluation["verdict"] == "fail"


def test_ac01_rejects_runtime_output_identity_drift(tmp_path: Path) -> None:
    # Given: the pinned runtime manifest initially binds exact output bytes.
    write_ac01_fixture(tmp_path)
    (tmp_path / "Resources/GenOffice/public-document-genoffice.js").write_text("tampered runtime output", encoding="utf-8")

    # When: AC-01 recomputes the runtime output identity.
    evaluation = run_contract({"action": "evaluate", "criterion": "AC-01", "root": str(tmp_path)})

    # Then: output drift fails independently of the authored port verdict.
    assert evaluation["verdict"] == "fail"


def test_ac01_rejects_forbidden_network_surface_with_current_hash(tmp_path: Path) -> None:
    # Given: a runtime output is rehashed after adding a forbidden network API.
    write_ac01_fixture(tmp_path)
    output_path = tmp_path / "Resources/GenOffice/public-document-genoffice.js"
    output_path.write_text("fetch('https://provider.invalid')", encoding="utf-8")
    manifest_path = tmp_path / "artifacts/provenance/genoffice-runtime-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    output_evidence = evidence(tmp_path, "Resources/GenOffice/public-document-genoffice.js")
    manifest["outputs"][0].update(
        {"path": "GenOffice/public-document-genoffice.js", "sha256": output_evidence["sha256"][7:], "sizeBytes": output_path.stat().st_size}
    )
    write_json(tmp_path, "artifacts/provenance/genoffice-runtime-manifest.json", manifest)

    # When: AC-01 scans the hash-current runtime surfaces.
    evaluation = run_contract({"action": "evaluate", "criterion": "AC-01", "root": str(tmp_path)})

    # Then: forbidden provider/network code fails even though every identity matches.
    assert evaluation["verdict"] == "fail"


def test_ac01_rejects_materialized_input_lock_drift(tmp_path: Path) -> None:
    # Given: the materialized runtime input lock no longer matches the checked source lock.
    write_ac01_fixture(tmp_path)
    lock_path = tmp_path / "artifacts/provenance/genoffice-runtime-input-lock.json"
    input_lock = json.loads(lock_path.read_text())
    input_lock["inputs"][0]["sha256"] = "0" * 64
    write_json(tmp_path, "artifacts/provenance/genoffice-runtime-input-lock.json", input_lock)

    # When: AC-01 compares the copied lock with its checked source and manifest.
    evaluation = run_contract({"action": "evaluate", "criterion": "AC-01", "root": str(tmp_path)})

    # Then: artifact drift fails instead of inheriting a stored runtime claim.
    assert evaluation["verdict"] == "fail"
    assert any(check["id"] == "runtime-manifest.input-lock" and not check["passed"] for check in evaluation["checks"])


def test_ac01_rejects_build_tool_lock_drift(tmp_path: Path) -> None:
    # Given: both checked lock copies claim a different build tool than the runtime manifest.
    write_ac01_fixture(tmp_path)
    for relative in ["GenOfficeFork/runtime-input-lock.json", "artifacts/provenance/genoffice-runtime-input-lock.json"]:
        lock_path = tmp_path / relative
        input_lock = json.loads(lock_path.read_text())
        input_lock["buildTool"]["version"] = "0.24.0"
        write_json(tmp_path, relative, input_lock)
    manifest_path = tmp_path / "artifacts/provenance/genoffice-runtime-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["inputLock"]["sha256"] = evidence(tmp_path, "GenOfficeFork/runtime-input-lock.json")["sha256"][7:]
    write_json(tmp_path, "artifacts/provenance/genoffice-runtime-manifest.json", manifest)

    # When: AC-01 recomputes the build-tool binding.
    evaluation = run_contract({"action": "evaluate", "criterion": "AC-01", "root": str(tmp_path)})

    # Then: an exact lock hash cannot conceal build-tool identity drift.
    assert evaluation["verdict"] == "fail"
    assert any(check["id"] == "runtime-manifest.input-lock" and not check["passed"] for check in evaluation["checks"])


def test_ac05_requires_consent_only_for_visual_flattening(tmp_path: Path) -> None:
    # Given: a complete four-format receipt has semantic-loss metadata but no visual flattening.
    write_ac05_fixture(tmp_path, flattening_consent=False)

    # When: AC-05 evaluates the receipt without a flattening consent flag.
    evaluation = run_contract({"action": "evaluate", "criterion": "AC-05", "root": str(tmp_path)})

    # Then: consent is not required for a receipt with no visual-only flattening output.
    assert evaluation["verdict"] == "pass"


def test_ac05_does_not_require_consent_for_blocked_flattening(tmp_path: Path) -> None:
    # Given: visual flattening is reported only for formats that publish no artifact.
    write_ac05_fixture(tmp_path, flattening_consent=False)
    validation_path = tmp_path / "artifacts/formats/export-validation-evidence.json"
    validation = json.loads(validation_path.read_text())
    receipt = validation["receipts"][0]
    receipt["publishedFormats"] = ["docx", "markdown"]
    receipt["blockedFormats"] = ["hwpx", "hwp"]
    receipt["results"] = [entry for entry in receipt["results"] if entry["format"] in {"docx", "markdown"}]
    receipt["lossReports"].append({"classification": "visual-only-flattening", "format": "hwpx"})
    write_json(tmp_path, "artifacts/formats/export-validation-evidence.json", validation)

    # When: AC-05 evaluates consent against actual published dispositions.
    evaluation = run_contract({"action": "evaluate", "criterion": "AC-05", "root": str(tmp_path)})

    # Then: an unmaterialized fallback does not create a consent requirement.
    assert evaluation["verdict"] == "pass"


def test_ac05_dispositions_exactly_partition_selected_formats(tmp_path: Path) -> None:
    # Given: one format is simultaneously claimed as published and failed.
    write_ac05_fixture(tmp_path, flattening_consent=True)
    validation_path = tmp_path / "artifacts/formats/export-validation-evidence.json"
    validation = json.loads(validation_path.read_text())
    validation["receipts"][0]["failedFormats"] = ["docx"]
    validation["receipts"][0]["failures"] = [{"format": "docx", "code": "runtime-failure"}]
    write_json(tmp_path, "artifacts/formats/export-validation-evidence.json", validation)

    # When: AC-05 derives the selected-format partition.
    evaluation = run_contract({"action": "evaluate", "criterion": "AC-05", "root": str(tmp_path)})

    # Then: overlapping dispositions fail even if the stored result is structurally valid.
    assert evaluation["verdict"] == "fail"


def test_ac05_failed_canonical_receipt_is_a_failure(tmp_path: Path) -> None:
    # Given: selected formats are exactly partitioned but one canonical export failed.
    write_ac05_fixture(tmp_path, flattening_consent=True)
    validation_path = tmp_path / "artifacts/formats/export-validation-evidence.json"
    validation = json.loads(validation_path.read_text())
    receipt = validation["receipts"][0]
    receipt["publishedFormats"] = ["hwpx", "hwp", "docx"]
    receipt["failedFormats"] = ["markdown"]
    receipt["failures"] = [{"format": "markdown", "code": "runtime-failure"}]
    receipt["results"] = [entry for entry in receipt["results"] if entry["format"] != "markdown"]
    write_json(tmp_path, "artifacts/formats/export-validation-evidence.json", validation)

    # When: AC-05 evaluates the canonical failed receipt.
    evaluation = run_contract({"action": "evaluate", "criterion": "AC-05", "root": str(tmp_path)})

    # Then: failure is explicit rather than being mistaken for a valid partition.
    assert evaluation["verdict"] == "fail"
    assert any(check["id"] == "exports.runtime-failures" and not check["passed"] for check in evaluation["checks"])
