from __future__ import annotations

import hashlib
import importlib.util
import json
import stat
import subprocess
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[1]
AUDITOR = ROOT / "scripts" / "qa" / "audit-ulw-evidence.py"


def _auditor_module():
    spec = importlib.util.spec_from_file_location("audit_ulw_evidence", AUDITOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_aggregate_auditor_declares_session_tree_and_override_inputs() -> None:
    result = subprocess.run(
        ["python3", str(AUDITOR), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    for option in ("--session", "--tree", "--out", "--goals", "--ledger"):
        assert option in result.stdout


def test_aggregate_auditor_fails_closed_for_unknown_session(tmp_path: Path) -> None:
    output = tmp_path / "audit.json"
    result = subprocess.run(
        [
            "python3",
            str(AUDITOR),
            "--session",
            "missing-session",
            "--tree",
            "deadbeef",
            "--out",
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode != 0
    assert "goals file is missing" in result.stderr
    assert not output.exists()


def test_artifact_validation_rejects_empty_json_and_truncated_binary_files(
    tmp_path: Path,
) -> None:
    auditor = _auditor_module()
    empty_json = tmp_path / "receipt.json"
    truncated_png = tmp_path / "screenshot.png"
    truncated_zip = tmp_path / "release.zip"
    empty_json.write_text("{}\n", encoding="utf-8")
    truncated_png.write_bytes(b"\x89PNG\r\n\x1a\n")
    truncated_zip.write_bytes(b"PK\x03\x04")

    defects: list[str] = []
    assert auditor.validate_artifact("receipt.json", empty_json, defects) is False
    assert auditor.validate_artifact("screenshot.png", truncated_png, defects) is False
    assert auditor.validate_artifact("release.zip", truncated_zip, defects) is False
    assert len(defects) == 3


def test_artifact_validation_rejects_unrelated_receipt_and_fake_transcript(
    tmp_path: Path,
) -> None:
    auditor = _auditor_module()
    receipt = tmp_path / "receipt.json"
    transcript = tmp_path / "transcript.txt"
    receipt.write_text('{"unrelated": true}\n', encoding="utf-8")
    transcript.write_text("fabricated evidence\n", encoding="utf-8")

    defects: list[str] = []
    assert auditor.validate_artifact("export/receipt.json", receipt, defects) is False
    assert auditor.validate_artifact("export/transcript.txt", transcript, defects) is False
    assert any("receipt contract" in defect for defect in defects)
    assert any("transcript contract" in defect for defect in defects)


def test_status_only_json_cannot_satisfy_required_evidence_contracts(
    tmp_path: Path,
) -> None:
    auditor = _auditor_module()
    for name in (
        "matrix.json",
        "result.json",
        "summary.json",
        "package-inspection.json",
        "action-log.json",
    ):
        artifact = tmp_path / name
        artifact.write_text('{"status": "pass"}\n', encoding="utf-8")
        defects: list[str] = []
        assert auditor.validate_artifact(f"evidence/{name}", artifact, defects) is False
        assert any("contract" in defect for defect in defects)


def test_shallow_plausible_json_cannot_fabricate_evidence(
    tmp_path: Path,
) -> None:
    auditor = _auditor_module()
    payloads = {
        "matrix.json": {
            "status": "pass",
            "formats": [],
            "caseCount": 0,
            "cases": [],
            "mismatches": [],
            "cleanup": "none",
        },
        "action-log.json": {
            "schemaVersion": 1,
            "scenario": "happy",
            "status": "pass",
            "actions": [],
            "cleanup": {},
        },
        "package-inspection.json": {
            "status": "pass",
            "cleanup": "none",
            "placeholder": True,
        },
        "summary.json": {
            "schemaVersion": 1,
            "status": "pass",
            "cleanup": "none",
        },
        "receipt.json": {
            "operationID": "fabricated",
            "selectedFormats": [],
            "publishedFormats": [],
            "blockedFormats": [],
            "failedFormats": [],
            "results": [],
        },
    }

    for name, payload in payloads.items():
        artifact = tmp_path / name
        artifact.write_text(json.dumps(payload), encoding="utf-8")
        defects: list[str] = []
        assert auditor.validate_artifact(f"fabricated/{name}", artifact, defects) is False
        assert defects


def test_release_verification_is_bound_to_archive_and_inventory_hashes(
    tmp_path: Path,
) -> None:
    auditor = _auditor_module()
    archive = tmp_path / "PublicDocument.zip"
    inventory = tmp_path / "PublicDocument.SHA256SUMS"
    verification = tmp_path / "PublicDocument.verification.json"
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("PublicDocument.app/Contents/Info.plist", b"plist")
    inventory.write_text("fixture inventory\n", encoding="utf-8")
    verification.write_text(
        json.dumps(
            {
                "archive": {
                    "file": archive.name,
                    "sha256": "0" * 64,
                },
                "bundle": {
                    "sha256Inventory": {
                        "file": inventory.name,
                        "sha256": hashlib.sha256(inventory.read_bytes()).hexdigest(),
                    }
                },
                "app": {"codesignVerification": "pass"},
                "verification": {
                    "freshTemporaryExtraction": True,
                    "archiveExtendedAttributes": "excluded",
                    "extractedInventoryComparison": "pass",
                    "sha256InventoryRecheck": "pass",
                },
            }
        ),
        encoding="utf-8",
    )

    defects: list[str] = []
    assert auditor.validate_artifact(
        "release/PublicDocument.verification.json",
        verification,
        defects,
    ) is False
    assert any("archive" in defect and "binding" in defect for defect in defects)


def test_release_verification_rejects_paths_outside_receipt_directory(
    tmp_path: Path,
) -> None:
    auditor = _auditor_module()
    release = tmp_path / "release"
    external = tmp_path / "external"
    release.mkdir()
    external.mkdir()
    archive = external / "external.zip"
    inventory = external / "external.SHA256SUMS"
    verification = release / "PublicDocument.verification.json"
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("PublicDocument.app/Contents/Info.plist", b"plist")
    inventory.write_text("external inventory\n", encoding="utf-8")
    verification.write_text(
        json.dumps(
            {
                "archive": {
                    "file": "../external/external.zip",
                    "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                },
                "bundle": {
                    "sha256Inventory": {
                        "file": "../external/external.SHA256SUMS",
                        "sha256": hashlib.sha256(inventory.read_bytes()).hexdigest(),
                    }
                },
                "app": {"codesignVerification": "pass"},
                "verification": {
                    "freshTemporaryExtraction": True,
                    "archiveExtendedAttributes": "excluded",
                    "extractedInventoryComparison": "pass",
                    "sha256InventoryRecheck": "pass",
                },
            }
        ),
        encoding="utf-8",
    )

    defects: list[str] = []
    assert auditor.validate_artifact(
        "release/PublicDocument.verification.json",
        verification,
        defects,
    ) is False
    assert any("outside release directory" in defect for defect in defects)


def test_release_verification_reopens_archive_and_checks_inventory_members(
    tmp_path: Path,
) -> None:
    auditor = _auditor_module()
    archive = tmp_path / "PublicDocument.zip"
    inventory = tmp_path / "PublicDocument.SHA256SUMS"
    verification = tmp_path / "PublicDocument.verification.json"
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("evil.txt", b"not an app")
    inventory.write_text(f"{'0' * 64}  unrelated\n", encoding="utf-8")
    verification.write_text(
        json.dumps(
            {
                "archive": {
                    "file": archive.name,
                    "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                },
                "bundle": {
                    "sha256Inventory": {
                        "file": inventory.name,
                        "sha256": hashlib.sha256(inventory.read_bytes()).hexdigest(),
                    }
                },
                "app": {"codesignVerification": "pass"},
                "verification": {
                    "freshTemporaryExtraction": True,
                    "archiveExtendedAttributes": "excluded",
                    "extractedInventoryComparison": "pass",
                    "sha256InventoryRecheck": "pass",
                },
            }
        ),
        encoding="utf-8",
    )

    defects: list[str] = []
    assert auditor.validate_artifact(
        "release/PublicDocument.verification.json",
        verification,
        defects,
    ) is False
    assert any("archive contents" in defect for defect in defects)


def test_zip_validation_rejects_symlink_members(tmp_path: Path) -> None:
    auditor = _auditor_module()
    archive = tmp_path / "symlink.zip"
    member = zipfile.ZipInfo("PublicDocument.app/Contents/link")
    member.create_system = 3
    member.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr(member, "/tmp")

    assert auditor.valid_zip(archive) is False
