from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

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
            "--trust-policy-sha256",
            fixture.policy_sha256_pin,
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


def copy_package(fixture: ReceiptFixture, root: Path) -> tuple[Path, Path]:
    secondary_root = root / "package-copy-secondary"
    shutil.copytree(fixture.artifact_root, secondary_root)
    secondary_manifest = root / "manifest-secondary.json"
    shutil.copy2(fixture.manifest_path, secondary_manifest)
    return secondary_root, secondary_manifest


def test_integrity_alone_cannot_override_authenticated_semantic_veto(
    tmp_path: Path,
) -> None:
    # Given: byte-identical copies and an authenticated external Stage 2 veto.
    fixture_root = tmp_path / "fixture"
    fixture_root.mkdir()
    fixture = build_fixture(
        fixture_root,
        final_approved=False,
        score_ppm=1000000,
    )
    secondary_root, secondary_manifest = copy_package(fixture, tmp_path)

    # When: the package-facing evaluator combines both independent gates.
    completed = run_package_verifier(
        fixture,
        secondary_root,
        secondary_manifest,
        tmp_path / "pins.sqlite3",
    )

    # Then: successful copy integrity cannot establish final acceptance.
    assert completed.returncode == 2
    assert completed.stderr == ""
    assert json.loads(completed.stdout) == {
        "decision": "NOT_ACCEPTED",
        "integrity_pass": True,
        "reason_codes": ["FINAL_APPROVAL_FALSE"],
        "receipt_digest": fixture.receipt_digest,
        "semantic_pass": False,
    }


def test_semantic_approval_alone_cannot_override_copy_integrity_failure(
    tmp_path: Path,
) -> None:
    # Given: valid authenticated approval but byte-distinct manifest copies whose
    # canonical 89-key content remains identical and bound to the receipt.
    fixture_root = tmp_path / "fixture"
    fixture_root.mkdir()
    fixture = build_fixture(fixture_root)
    secondary_root, secondary_manifest = copy_package(fixture, tmp_path)
    manifest = json.loads(secondary_manifest.read_text(encoding="utf-8"))
    secondary_manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # When: the package-facing evaluator combines both independent gates.
    completed = run_package_verifier(
        fixture,
        secondary_root,
        secondary_manifest,
        tmp_path / "pins.sqlite3",
    )

    # Then: successful authenticated semantics cannot establish final acceptance.
    assert completed.returncode == 2
    assert completed.stderr == ""
    assert json.loads(completed.stdout) == {
        "decision": "NOT_ACCEPTED",
        "integrity_pass": False,
        "reason_codes": ["INTEGRITY_COPY_MISMATCH"],
        "receipt_digest": fixture.receipt_digest,
        "semantic_pass": True,
    }
