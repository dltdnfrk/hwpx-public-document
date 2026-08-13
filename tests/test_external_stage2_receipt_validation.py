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


def run_verifier(fixture: ReceiptFixture) -> subprocess.CompletedProcess[str]:
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
            NOW,
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def test_accepts_only_fully_authenticated_and_bound_receipt(tmp_path: Path) -> None:
    # Given: an external receipt signed by an authorized key and bound to every input.
    fixture = build_fixture(tmp_path)

    # When: the receipt is evaluated through the package-facing verifier.
    completed = run_verifier(fixture)

    # Then: the external semantic gate accepts and reports the canonical receipt digest.
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "decision": "ACCEPTED",
        "reason_codes": [],
        "receipt_digest": fixture.receipt_digest,
        "semantic_pass": True,
    }


@pytest.mark.parametrize(
    ("approved", "score_ppm", "expected_reasons"),
    [
        (False, 1000000, ["FINAL_APPROVAL_FALSE"]),
        (True, 799999, ["FIELD_INCONSISTENCY", "SCORE_BELOW_THRESHOLD"]),
    ],
)
def test_external_semantic_veto_and_threshold_are_authoritative(
    tmp_path: Path,
    approved: bool,
    score_ppm: int,
    expected_reasons: list[str],
) -> None:
    # Given: the manifest claims approval but authenticated Stage 2 does not qualify.
    fixture = build_fixture(tmp_path, final_approved=approved, score_ppm=score_ppm)

    # When: the signed external decision is evaluated at the semantic boundary.
    completed = run_verifier(fixture)

    # Then: only the signed Stage 2 verdict and native integer score control acceptance.
    assert completed.returncode == 2
    assert json.loads(completed.stdout)["reason_codes"] == expected_reasons


@pytest.mark.parametrize(
    ("mutation", "expected_reason"),
    [
        ("unknown_envelope_field", "RECEIPT_SCHEMA_INVALID"),
        ("wrong_envelope_version", "RECEIPT_SCHEMA_INVALID"),
        ("padded_payload", "RECEIPT_SCHEMA_INVALID"),
        ("unknown_key", "SIGNER_UNAUTHORIZED"),
    ],
)
def test_rejects_non_closed_or_noncanonical_envelope_before_semantics(
    tmp_path: Path,
    mutation: str,
    expected_reason: str,
) -> None:
    # Given: the outer receipt protocol is no longer closed and canonical.
    fixture = build_fixture(tmp_path)
    envelope = json.loads(fixture.receipt_path.read_text(encoding="utf-8"))
    if mutation == "unknown_envelope_field":
        envelope["approval"] = "PASS"
    elif mutation == "wrong_envelope_version":
        envelope["schema_version"] = 2
    elif mutation == "padded_payload":
        envelope["payload"] += "="
    elif mutation == "unknown_key":
        envelope["key_id"] = "unknown-key"
    fixture.receipt_path.write_text(json.dumps(envelope), encoding="utf-8")

    # When: the invalid envelope is evaluated.
    completed = run_verifier(fixture)

    # Then: the protocol fails closed before candidate semantic claims are consulted.
    assert completed.returncode == 2
    assert json.loads(completed.stdout)["reason_codes"] == [expected_reason]


@pytest.mark.parametrize(
    ("target", "expected_reason"),
    [
        ("signature", "SIGNATURE_INVALID"),
        ("policy", "POLICY_MISMATCH"),
        ("execution", "EXECUTION_MISMATCH"),
        ("artifact", "ARTIFACT_BINDING_MISMATCH"),
        ("manifest", "MANIFEST_BINDING_MISMATCH"),
        ("request", "REQUEST_BINDING_MISMATCH"),
        ("result", "RESULT_BINDING_MISMATCH"),
    ],
)
def test_fails_closed_when_authenticated_context_or_binding_changes(
    tmp_path: Path,
    target: str,
    expected_reason: str,
) -> None:
    # Given: one component of an otherwise valid receipt evaluation is changed.
    fixture = build_fixture(tmp_path)
    if target == "signature":
        envelope = json.loads(fixture.receipt_path.read_text(encoding="utf-8"))
        replacement = "B" if envelope["signature"].startswith("A") else "A"
        envelope["signature"] = replacement + envelope["signature"][1:]
        fixture.receipt_path.write_text(json.dumps(envelope), encoding="utf-8")
    elif target == "policy":
        policy = json.loads(fixture.policy_path.read_text(encoding="utf-8"))
        policy["keys"][0]["authorized_until"] = "2026-08-15T00:00:00.000Z"
        fixture.policy_path.write_text(json.dumps(policy), encoding="utf-8")
    elif target == "execution":
        pass
    elif target == "artifact":
        (fixture.artifact_root / "document.bin").write_bytes(b"changed artifact")
    elif target == "manifest":
        manifest = json.loads(fixture.manifest_path.read_text(encoding="utf-8"))
        manifest["manifest_key_00"] = "changed"
        fixture.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    elif target == "request":
        request = json.loads(fixture.request_path.read_text(encoding="utf-8"))
        request["requested_at"] = "2026-08-13T11:59:58.000Z"
        fixture.request_path.write_text(json.dumps(request), encoding="utf-8")
    elif target == "result":
        result = json.loads(fixture.result_path.read_text(encoding="utf-8"))
        result["completed_at"] = "2026-08-13T12:00:01.000Z"
        fixture.result_path.write_text(json.dumps(result), encoding="utf-8")

    # When: the changed evaluation is verified.
    if target == "execution":
        completed = subprocess.run(
            [
                *run_command(fixture),
                "--execution-id",
                "different-execution",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
    else:
        completed = run_verifier(fixture)

    # Then: no candidate-authored data can rescue the failed provenance or binding.
    assert completed.returncode == 2
    assert json.loads(completed.stdout)["reason_codes"] == [expected_reason]


def run_command(fixture: ReceiptFixture) -> list[str]:
    return [
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
        "--now",
        NOW,
    ]
