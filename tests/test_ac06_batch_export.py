from __future__ import annotations

import json
import hashlib
import os
import subprocess
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import TypedDict


ROOT = Path(__file__).resolve().parents[1]


class PublicationIntent(TypedDict):
    destinationFile: str
    expectedArtifactHash: str


class RequiredBatchItem(TypedDict):
    documentID: str
    destinationFile: str
    format: str
    state: str
    diagnosticCode: str
    progressCompleted: int
    progressTotal: int


class BatchItem(RequiredBatchItem, total=False):
    artifactHash: str
    documentDisplayName: str
    publicationIntent: PublicationIntent


class DestinationIntegrity(TypedDict):
    destinationFile: str
    beforeByteCount: int
    afterByteCount: int
    beforeSHA256: str
    afterSHA256: str
    existingBytesPreserved: bool


class RequiredBatchManifest(TypedDict):
    schemaVersion: int
    operationID: str
    retryOfOperationID: str | None
    state: str
    cleanupState: str
    manifestPath: str
    items: list[BatchItem]


class BatchManifest(RequiredBatchManifest, total=False):
    destinationIntegrity: DestinationIntegrity


class RequiredRecoveryReceipt(TypedDict):
    root: str
    recovered: BatchManifest
    retry: BatchManifest


class RecoveryReceipt(RequiredRecoveryReceipt, total=False):
    reconciledAfterMove: BatchManifest
    startupRecovered: list[BatchManifest]
    hashMismatchRecovered: BatchManifest
    nonRegularRecovered: BatchManifest
    pathEscapeRecovered: BatchManifest
    legacyV1Recovered: BatchManifest
    manifestlessOperationID: str
    manifestlessOperationExists: bool
    manifestlessManifestExists: bool


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


def _run_batch_scenario(
    root: Path,
    scenario: str,
    *,
    mutate_existing_destination: bool = False,
) -> BatchManifest:
    environment = os.environ.copy()
    if mutate_existing_destination:
        environment["PUBLIC_DOCUMENT_AC06_TEST_MUTATE_EXISTING_DESTINATION"] = "1"
    result = subprocess.run(
        [str(_app_binary()), "--batch-export-self-test", str(root), scenario],
        cwd=ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    receipt: BatchManifest = json.loads(result.stdout)
    return receipt


def _run_recovery_scenario(root: Path, scenario: str) -> RecoveryReceipt:
    result = subprocess.run(
        [str(_app_binary()), "--batch-export-self-test", str(root), scenario],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    receipt: RecoveryReceipt = json.loads(result.stdout)
    return receipt


def test_batch_preserves_validated_siblings_when_one_item_fails(tmp_path: Path) -> None:
    # Given: two documents, two formats, and one injected document-format failure.
    export_root = tmp_path / "partial-failure"

    # When: the app executes the batch through its native CLI surface.
    receipt = _run_batch_scenario(export_root, "partial-failure")

    # Then: the manifest records progress per item and keeps three validated siblings.
    assert receipt["operationID"] == "batch-ac06-partial"
    assert receipt["state"] == "completed-with-errors"
    items = receipt["items"]
    assert len(items) == 4
    assert [item["state"] for item in items].count("published") == 3
    failed = next(item for item in items if item["state"] == "failed")
    assert failed["documentID"] == "document-ac06-b"
    assert failed["format"] == "docx"
    assert failed["diagnosticCode"] == "injected-process-failure"
    assert all(item["progressCompleted"] <= item["progressTotal"] for item in items)
    assert (export_root / "생활안전-계획.docx").is_file()
    assert (export_root / "생활안전-계획.md").is_file()
    assert (export_root / "시설점검-보고.md").is_file()
    assert not (export_root / "시설점검-보고.docx").exists()
    manifest = json.loads(Path(receipt["manifestPath"]).read_text(encoding="utf-8"))
    assert manifest == receipt


def test_cancellation_keeps_published_item_and_cleans_unfinished_outputs(tmp_path: Path) -> None:
    # Given: a four-item batch configured to cancel after its first publication.
    export_root = tmp_path / "cancelled"

    # When: cancellation is observed between document-format items.
    receipt = _run_batch_scenario(export_root, "cancel-after-first")

    # Then: the first success remains and every unfinished item is explicitly cancelled.
    assert receipt["state"] == "cancelled"
    states = [item["state"] for item in receipt["items"]]
    assert states == ["published", "cancelled", "cancelled", "cancelled"]
    assert (export_root / "생활안전-계획.docx").is_file()
    assert list(export_root.rglob("*.tmp")) == []
    assert receipt["cleanupState"] == "clean"


def test_cancellation_before_publication_removes_validated_staging(tmp_path: Path) -> None:
    # Given: cancellation is requested when the first item reaches validated staging.
    export_root = tmp_path / "cancel-before-publication"

    # When: the coordinator observes cancellation before atomic publication.
    receipt = _run_batch_scenario(export_root, "cancel-before-publication")

    # Then: the item is cancelled, its temporary artifact is removed, and nothing publishes.
    assert receipt["state"] == "cancelled"
    assert receipt["items"][0]["state"] == "cancelled"
    assert receipt["items"][0]["progressCompleted"] == 3
    assert receipt["cleanupState"] == "clean"
    assert not (export_root / "생활안전-계획.docx").exists()
    assert list(export_root.rglob("*.tmp")) == []


def test_existing_destination_is_never_overwritten(tmp_path: Path) -> None:
    # Given: one destination already contains user-owned bytes.
    export_root = tmp_path / "existing"
    export_root.mkdir()
    existing = export_root / "생활안전-계획.docx"
    existing.write_bytes(b"user-owned-existing-file")

    # When: the same destination is included in a two-item batch.
    receipt = _run_batch_scenario(export_root, "existing-destination")

    # Then: the existing bytes remain untouched while its sibling publishes.
    assert existing.read_bytes() == b"user-owned-existing-file"
    refused = next(item for item in receipt["items"] if item["format"] == "docx")
    assert refused["state"] == "failed"
    assert refused["diagnosticCode"] == "destination-exists"
    assert (export_root / "생활안전-계획.md").is_file()
    integrity = receipt.get("destinationIntegrity")
    assert integrity is not None
    assert unicodedata.normalize("NFC", integrity["destinationFile"]) == existing.name
    assert integrity["beforeByteCount"] == integrity["afterByteCount"]
    assert integrity["beforeSHA256"] == integrity["afterSHA256"]
    assert integrity["existingBytesPreserved"] is True


def test_existing_destination_integrity_detects_mutated_bytes(tmp_path: Path) -> None:
    # Given: an existing destination and an evidence-only mutation after refusal.
    export_root = tmp_path / "existing-tampered"
    export_root.mkdir()
    existing = export_root / "생활안전-계획.docx"
    existing.write_bytes(b"user-owned-existing-file")

    # When: the native self-test measures exact bytes after the mutation hook runs.
    receipt = _run_batch_scenario(
        export_root,
        "existing-destination",
        mutate_existing_destination=True,
    )

    # Then: the independently measured integrity attestation cannot claim preservation.
    integrity = receipt.get("destinationIntegrity")
    assert integrity is not None
    assert integrity["beforeSHA256"] != integrity["afterSHA256"]
    assert integrity["existingBytesPreserved"] is False


def test_crash_and_disk_full_recover_manifest_cleanup_and_retry_lineage(
    tmp_path: Path,
) -> None:
    # Given: crash-before-publication and disk-full-before-publication fault points.
    crash_root = tmp_path / "crash"
    disk_root = tmp_path / "disk-full"

    # When: startup recovery runs and the failed work is retried with a new operation ID.
    crash = _run_recovery_scenario(crash_root, "crash-and-retry")
    disk = _run_recovery_scenario(disk_root, "disk-full-and-retry")

    # Then: crashes recover as interrupted, while disk-full is durably classified.
    assert crash["recovered"]["state"] == "interrupted"
    assert crash["recovered"]["items"][0]["diagnosticCode"] == (
        "publication-artifact-missing"
    )
    assert disk["recovered"]["state"] == "completed-with-errors"
    assert disk["recovered"]["items"][0]["diagnosticCode"] == "disk-full"

    for receipt, previous_id in (
        (crash, "batch-ac06-crashed"),
        (disk, "batch-ac06-disk-full"),
    ):
        assert receipt["recovered"]["cleanupState"] == "clean"
        assert receipt["recovered"]["items"][0]["state"] == "failed"
        assert receipt["retry"]["operationID"] != previous_id
        assert receipt["retry"]["retryOfOperationID"] == previous_id
        assert receipt["retry"]["state"] == "completed"
        assert receipt["retry"]["items"][0]["state"] == "published"
        assert (
            receipt["retry"]["items"][0]["destinationFile"]
            == receipt["recovered"]["items"][0]["destinationFile"]
        )
        assert list(Path(receipt["root"]).rglob("*.tmp")) == []


def test_crash_after_move_reconciles_hash_and_manifestless_startup_isolated(
    tmp_path: Path,
) -> None:
    # Given: one crash happens after the artifact move but before the published manifest,
    # and startup also sees a separate operation directory with no manifest.
    receipt = _run_recovery_scenario(tmp_path / "durable-recovery", "crash-and-retry")

    # Then: exact expected bytes are promoted to published instead of being retried.
    reconciled = receipt.get("reconciledAfterMove")
    assert reconciled is not None
    assert reconciled["state"] == "completed"
    assert reconciled["cleanupState"] == "clean"
    item = reconciled["items"][0]
    assert item["state"] == "published"
    assert item["documentID"] == "document-ac06-a"
    assert item.get("documentDisplayName") == "생활안전 계획"
    artifact_hash = item.get("artifactHash")
    assert artifact_hash is not None
    intent = item.get("publicationIntent")
    assert intent is not None
    assert intent["destinationFile"] == item["destinationFile"]
    assert intent["expectedArtifactHash"] == artifact_hash
    artifact = Path(receipt["root"]) / item["destinationFile"]
    assert "sha256:" + hashlib.sha256(artifact.read_bytes()).hexdigest() == (
        intent["expectedArtifactHash"]
    )
    assert json.loads(Path(reconciled["manifestPath"]).read_text(encoding="utf-8")) == (
        reconciled
    )

    # And: a manifest-less sibling cannot abort recovery of a valid interrupted operation.
    assert receipt.get("manifestlessOperationID") == "batch-ac06-pre-manifest"
    assert receipt.get("manifestlessOperationExists") is True
    assert receipt.get("manifestlessManifestExists") is False
    startup_recovered = receipt.get("startupRecovered")
    assert startup_recovered is not None
    assert [manifest["operationID"] for manifest in startup_recovered] == [
        "batch-ac06-startup-recoverable"
    ]
    assert startup_recovered[0]["state"] == "interrupted"
    assert startup_recovered[0]["items"][0]["diagnosticCode"] == (
        "publication-artifact-missing"
    )

    hash_mismatch = receipt.get("hashMismatchRecovered")
    assert hash_mismatch is not None
    mismatch_item = hash_mismatch["items"][0]
    assert mismatch_item["diagnosticCode"] == "publication-artifact-hash-mismatch"
    mismatch_artifact = Path(receipt["root"]) / mismatch_item["destinationFile"]
    assert mismatch_artifact.read_bytes() == b"ac06-hash-mismatch"

    non_regular = receipt.get("nonRegularRecovered")
    assert non_regular is not None
    non_regular_item = non_regular["items"][0]
    assert non_regular_item["diagnosticCode"] == "publication-artifact-missing"
    assert (Path(receipt["root"]) / non_regular_item["destinationFile"]).is_symlink()

    path_escape = receipt.get("pathEscapeRecovered")
    assert path_escape is not None
    escape_item = path_escape["items"][0]
    assert escape_item["diagnosticCode"] == "publication-path-invalid"
    assert escape_item["destinationFile"] == "../ac06-outside.docx"
    assert not (Path(receipt["root"]).parent / "ac06-outside.docx").exists()

    legacy = receipt.get("legacyV1Recovered")
    assert legacy is not None
    assert legacy["schemaVersion"] == 1
    assert legacy["state"] == "interrupted"
    legacy_item = legacy["items"][0]
    assert legacy_item["diagnosticCode"] == "publication-artifact-missing"
    assert "documentDisplayName" not in legacy_item
    assert "publicationIntent" not in legacy_item


def test_studio_exposes_batch_progress_cancellation_and_recovery() -> None:
    # Given: the shipped Studio and native bridge sources.
    html = (ROOT / "Resources" / "Studio" / "index.html").read_text(encoding="utf-8")
    script = (ROOT / "Resources" / "Studio" / "app.js").read_text(encoding="utf-8")
    host = (ROOT / "Sources" / "PublicDocumentApp" / "main.swift").read_text(encoding="utf-8")

    # When/Then: batch selection, per-item progress, cancellation, and recovery are operable.
    assert "여러 문서 일괄 내보내기" in html
    assert 'data-action="cancel-batch-export"' in html
    assert 'data-action="retry-batch-export"' in html
    assert 'aria-label="문서별 형식 내보내기 진행률"' in html
    assert "batchExportProgress" in script
    assert "batchExportRecovered" in script
    assert "projectBridge('cancelBatchExport'" in script
    assert "projectBridge('retryBatchExport'" in script
    assert 'case "batchExport":' in host
    assert 'case "cancelBatchExport":' in host
    assert 'case "retryBatchExport":' in host
