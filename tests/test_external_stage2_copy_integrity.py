from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.external_stage2.receipt_fixture import (
    EXECUTION_ID,
    NOW,
    ReceiptFixture,
    build_fixture,
)

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_VERIFIER = ROOT / "scripts/external-stage2/verify_package.py"


def run_package_verifier(
    fixture: ReceiptFixture,
    secondary_root: Path,
    secondary_manifest: Path,
    pin_db: Path,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(PACKAGE_VERIFIER),
            "--receipt",
            str(fixture.receipt_path),
            "--trust-policy",
            str(fixture.policy_path),
            "--request",
            str(fixture.request_path),
            "--result",
            str(fixture.result_path),
            "--primary-manifest",
            str(fixture.manifest_path),
            "--secondary-manifest",
            str(secondary_manifest),
            "--primary-artifact-root",
            str(fixture.artifact_root),
            "--secondary-artifact-root",
            str(secondary_root),
            "--execution-id",
            EXECUTION_ID,
            "--pin-db",
            str(pin_db),
            "--now",
            NOW,
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def matching_copies(
    tmp_path: Path,
) -> tuple[ReceiptFixture, Path, Path, Path]:
    fixture_root = tmp_path / "fixture"
    fixture_root.mkdir()
    fixture = build_fixture(fixture_root)
    secondary_root = tmp_path / "package-copy-secondary"
    shutil.copytree(fixture.artifact_root, secondary_root)
    secondary_manifest = tmp_path / "manifest-secondary.json"
    shutil.copy2(fixture.manifest_path, secondary_manifest)
    return fixture, secondary_root, secondary_manifest, tmp_path / "pins.sqlite3"


def output(completed: subprocess.CompletedProcess[str]) -> dict[str, object]:
    assert completed.stderr == ""
    return json.loads(completed.stdout)


def test_matching_intact_package_copies_are_accepted(tmp_path: Path) -> None:
    # Given: two byte-identical package copies and one valid external receipt.
    fixture, secondary_root, secondary_manifest, pin_db = matching_copies(tmp_path)

    # When: the package-facing dual-gate evaluator checks both copies.
    completed = run_package_verifier(
        fixture,
        secondary_root,
        secondary_manifest,
        pin_db,
    )

    # Then: copy integrity and external semantics jointly accept the package.
    assert completed.returncode == 0
    assert output(completed) == {
        "decision": "ACCEPTED",
        "integrity_pass": True,
        "reason_codes": [],
        "receipt_digest": fixture.receipt_digest,
        "semantic_pass": True,
    }


@pytest.mark.parametrize("copy_name", ["primary", "secondary"])
def test_tampering_either_package_copy_is_not_accepted(
    tmp_path: Path,
    copy_name: str,
) -> None:
    # Given: two initially identical copies with one copy changed after receipt issuance.
    fixture, secondary_root, secondary_manifest, pin_db = matching_copies(tmp_path)
    target_root = fixture.artifact_root if copy_name == "primary" else secondary_root
    (target_root / "document.bin").write_bytes(b"tampered package bytes")

    # When: the package-facing evaluator independently checks both package copies.
    completed = run_package_verifier(
        fixture,
        secondary_root,
        secondary_manifest,
        pin_db,
    )

    # Then: both copy mismatch and current receipt binding failure are reported.
    assert completed.returncode == 2
    assert output(completed) == {
        "decision": "NOT_ACCEPTED",
        "integrity_pass": False,
        "reason_codes": [
            "ARTIFACT_BINDING_MISMATCH",
            "INTEGRITY_COPY_MISMATCH",
        ],
        "receipt_digest": fixture.receipt_digest,
        "semantic_pass": False,
    }


def test_missing_package_copy_is_not_accepted(tmp_path: Path) -> None:
    # Given: the primary copy and semantic evidence exist but the second copy does not.
    fixture_root = tmp_path / "fixture"
    fixture_root.mkdir()
    fixture = build_fixture(fixture_root)
    missing_root = tmp_path / "package-copy-secondary"
    secondary_manifest = tmp_path / "manifest-secondary.json"
    shutil.copy2(fixture.manifest_path, secondary_manifest)

    # When: the package-facing evaluator checks the incomplete pair.
    completed = run_package_verifier(
        fixture,
        missing_root,
        secondary_manifest,
        tmp_path / "pins.sqlite3",
    )

    # Then: copy existence fails closed and acceptance is impossible.
    assert completed.returncode == 2
    assert output(completed) == {
        "decision": "NOT_ACCEPTED",
        "integrity_pass": False,
        "reason_codes": [
            "ARTIFACT_BINDING_MISMATCH",
            "INTEGRITY_COPY_MISSING",
        ],
        "receipt_digest": fixture.receipt_digest,
        "semantic_pass": False,
    }
