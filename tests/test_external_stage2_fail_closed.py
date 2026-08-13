from __future__ import annotations

import json
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
VERIFIER = ROOT / "scripts/external-stage2/verify_receipt.py"


def run_verifier(
    fixture: ReceiptFixture,
    *,
    now: str = NOW,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(VERIFIER),
            "--receipt",
            str(fixture.receipt_path),
            "--trust-policy",
            str(fixture.policy_path),
            "--request",
            str(fixture.request_path),
            "--result",
            str(fixture.result_path),
            "--manifest",
            str(fixture.manifest_path),
            "--artifact-root",
            str(fixture.artifact_root),
            "--execution-id",
            EXECUTION_ID,
            "--now",
            now,
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def assert_not_accepted(
    completed: subprocess.CompletedProcess[str],
    expected_reasons: list[str],
) -> None:
    assert completed.returncode == 2, completed.stderr
    assert json.loads(completed.stdout) == {
        "decision": "NOT_ACCEPTED",
        "reason_codes": expected_reasons,
        "receipt_digest": None,
        "semantic_pass": False,
    }


def test_candidate_authored_semantic_claims_cannot_override_external_rejection(
    tmp_path: Path,
) -> None:
    # Given: all compatibility claims in the candidate manifest are maximally positive.
    fixture = build_fixture(tmp_path, final_approved=False, score_ppm=1000000)
    manifest = json.loads(fixture.manifest_path.read_text(encoding="utf-8"))
    assert manifest["manifest_key_00"] == "PASS"
    assert manifest["manifest_key_01"] is True
    assert manifest["manifest_key_02"] == 1000000
    assert manifest["manifest_key_03"] == {"independentlyProduced": True}

    # When: authenticated external Stage 2 vetoes the bound package.
    completed = run_verifier(fixture)

    # Then: candidate-authored PASS, approval, score, and provenance have no authority.
    assert completed.returncode == 2, completed.stderr
    assert json.loads(completed.stdout) == {
        "decision": "NOT_ACCEPTED",
        "reason_codes": ["FINAL_APPROVAL_FALSE"],
        "receipt_digest": fixture.receipt_digest,
        "semantic_pass": False,
    }


def test_missing_external_receipt_fails_closed(tmp_path: Path) -> None:
    # Given: the candidate package exists but its external receipt does not.
    fixture = build_fixture(tmp_path)
    fixture.receipt_path.unlink()

    # When: the package-facing verifier evaluates the candidate.
    completed = run_verifier(fixture)

    # Then: missing semantic authority is classified and cannot authorize the package.
    assert_not_accepted(completed, ["RECEIPT_MISSING"])


@pytest.mark.parametrize(
    ("sidecar", "expected_reason"),
    [
        ("receipt", "RECEIPT_PARSE_INVALID"),
        ("policy", "POLICY_SNAPSHOT_INVALID"),
        ("request", "REQUEST_SCHEMA_INVALID"),
        ("result", "RESULT_SCHEMA_INVALID"),
    ],
)
def test_malformed_external_evidence_fails_closed(
    tmp_path: Path,
    sidecar: str,
    expected_reason: str,
) -> None:
    # Given: one required external input is not valid JSON.
    fixture = build_fixture(tmp_path)
    path = {
        "receipt": fixture.receipt_path,
        "policy": fixture.policy_path,
        "request": fixture.request_path,
        "result": fixture.result_path,
    }[sidecar]
    path.write_bytes(b"not-json")

    # When: the malformed evidence is evaluated.
    completed = run_verifier(fixture)

    # Then: its stable boundary-specific reason is returned with exit 2.
    assert_not_accepted(completed, [expected_reason])


def test_unauthenticated_receipt_fails_closed(tmp_path: Path) -> None:
    # Given: an otherwise closed receipt has a modified Ed25519 signature.
    fixture = build_fixture(tmp_path)
    envelope = json.loads(fixture.receipt_path.read_text(encoding="utf-8"))
    signature = envelope["signature"]
    envelope["signature"] = ("A" if signature[0] != "A" else "B") + signature[1:]
    fixture.receipt_path.write_text(json.dumps(envelope), encoding="utf-8")

    # When: signature authentication runs.
    completed = run_verifier(fixture)

    # Then: unauthenticated semantic evidence never reaches authorization.
    assert_not_accepted(completed, ["SIGNATURE_INVALID"])


def test_mismatched_artifact_binding_fails_closed(tmp_path: Path) -> None:
    # Given: the signed receipt is valid but the evaluated candidate bytes changed.
    fixture = build_fixture(tmp_path)
    (fixture.artifact_root / "document.bin").write_bytes(b"unbound candidate bytes")

    # When: current artifact bindings are recomputed.
    completed = run_verifier(fixture)

    # Then: the receipt cannot authorize different artifact bytes.
    assert_not_accepted(completed, ["ARTIFACT_BINDING_MISMATCH"])


@pytest.mark.parametrize(
    ("now", "expected_reason"),
    [
        ("2026-08-13T12:10:00.001Z", "RECEIPT_STALE"),
        ("2026-08-13T11:59:29.999Z", "RECEIPT_FUTURE"),
    ],
)
def test_receipt_outside_freshness_window_fails_closed(
    tmp_path: Path,
    now: str,
    expected_reason: str,
) -> None:
    # Given: valid external evidence lies one millisecond outside a freshness boundary.
    fixture = build_fixture(tmp_path)

    # When: freshness is evaluated against the orchestrator-supplied time.
    completed = run_verifier(fixture, now=now)

    # Then: stale and future receipts fail with their stable reason codes.
    assert_not_accepted(completed, [expected_reason])


def test_inconsistent_external_approval_and_score_fails_closed(tmp_path: Path) -> None:
    # Given: authenticated Stage 2 claims approval below the inclusive score threshold.
    fixture = build_fixture(tmp_path, final_approved=True, score_ppm=799999)

    # When: the signed semantic fields are evaluated.
    completed = run_verifier(fixture)

    # Then: all safe semantic findings are sorted, unique, and fail with exit 2.
    assert completed.returncode == 2, completed.stderr
    assert json.loads(completed.stdout) == {
        "decision": "NOT_ACCEPTED",
        "reason_codes": ["FIELD_INCONSISTENCY", "SCORE_BELOW_THRESHOLD"],
        "receipt_digest": fixture.receipt_digest,
        "semantic_pass": False,
    }
